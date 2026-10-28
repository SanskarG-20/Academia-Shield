const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');
const { Server } = require('socket.io');
const { io: connect } = require('socket.io-client');
const jwt = require('jsonwebtoken');
const Device = require('../dist/models/Device').default;
const Student = require('../dist/models/Student').default;
const Professor = require('../dist/models/Professor').default;
const Session = require('../dist/models/Session').default;
const Rule = require('../dist/models/Rule').default;
const Claim = require('../dist/models/EnrollmentClaim').default;
const clock = require('../dist/services/sessionClock');
const { authenticateDevice, deviceAuth, hashCredential } = require('../dist/middleware/deviceAuth');
const { policyForDevice } = require('../dist/services/devicePolicy');
const { enrollDevice } = require('../dist/controllers/enrollmentController');
const { joinSession } = require('../dist/controllers/sessionController');
const { createRule } = require('../dist/controllers/ruleController');
const { authorizeSessionRoom, setupSocket } = require('../dist/services/socketService');
const logRoutes = require('../dist/routes/logRoutes').default;

function response() {
  return { code: 200, body: null, status(code) { this.code = code; return this; }, json(body) { this.body = body; return this; } };
}

test('device credential authenticates only its own non-revoked record', async t => {
  const secret = crypto.randomBytes(32).toString('base64url');
  const id = 'aaaaaaaaaaaaaaaaaaaaaaaa';
  const record = { _id: id, studentId: 'student-a', credentialHash: hashCredential(secret), revokedAt: null };
  t.mock.method(Device, 'findById', query => ({ select: async () => query === id ? record : null }));
  assert.equal(await authenticateDevice(`Device ${id}.${secret}`), record);
  assert.equal(await authenticateDevice(`Device ${id}.${crypto.randomBytes(32).toString('base64url')}`), null);
  record.revokedAt = new Date();
  assert.equal(await authenticateDevice(`Device ${id}.${secret}`), null);
});

test('missing device credential is rejected by protected API', async () => {
  const res = response();
  await deviceAuth({ headers: {} }, res, () => { throw new Error('must not pass'); });
  assert.equal(res.code, 401);
});

test('browser logs route has no activity write endpoint', () => {
  assert.equal(logRoutes.stack.some(layer => layer.route?.methods?.post), false);
});

test('oversized rule sets are rejected before they reach devices', async () => {
  const res = response();
  await createRule({ body: { name: 'unsafe', mode: 'Blocklist', websites: Array(201).fill('example.com'), applications: [] }, user: { id: 'prof-a' } }, res);
  assert.equal(res.code, 400);
});

test('policy queries are bound to the authenticated student and device', async t => {
  t.mock.method(clock, 'reconcileSessions', async () => ({ started: 0, ended: 0 }));
  const seen = [];
  t.mock.method(Student, 'findById', id => ({ select: async () => ({ joinedBatches: [id === 'student-a' ? 'batch-a' : 'batch-b'] }) }));
  t.mock.method(Session, 'find', query => {
    seen.push(query);
    const sid = String(query.joinedStudentIds);
    const batch = query.batchIds.$in[0];
    return { select: async () => [{ _id: sid === 'student-a' ? 'session-a' : 'session-b', title: 'Lab', endTime: new Date(Date.now() + 60_000), professorId: 'prof-a', ruleSetId: sid === 'student-a' ? 'rule-a' : 'rule-b', batchIds: [batch] }] };
  });
  t.mock.method(Rule, 'findOne', async query => ({ websites: [query._id + '.example'], applications: [query._id + '.exe'] }));
  const a = await policyForDevice({ _id: 'device-a', studentId: 'student-a', revokedAt: null });
  const b = await policyForDevice({ _id: 'device-b', studentId: 'student-b', revokedAt: null });
  assert.deepEqual(a.blockedDomains, ['rule-a.example']);
  assert.deepEqual(b.blockedDomains, ['rule-b.example']);
  assert.equal(a.deviceId, 'device-a');
  assert.equal(b.deviceId, 'device-b');
  assert.equal(seen[0].joinedStudentIds, 'student-a');
  assert.deepEqual(seen[1].batchIds.$in, ['batch-b']);
  assert.ok(new Date(a.expiresAt) <= new Date(a.active_sessions[0].ends_at));
  await assert.rejects(() => policyForDevice({ _id: 'revoked', studentId: 'student-a', revokedAt: new Date() }), /revoked/);
});

test('expired sessions never produce an active policy', async t => {
  t.mock.method(clock, 'reconcileSessions', async () => ({ started: 0, ended: 1 }));
  t.mock.method(Student, 'findById', () => ({ select: async () => ({ joinedBatches: ['batch-a'] }) }));
  t.mock.method(Session, 'find', query => {
    assert.ok(query.endTime.$gt instanceof Date);
    return { select: async () => [] };
  });
  const policy = await policyForDevice({ _id: 'device-a', studentId: 'student-a', revokedAt: null });
  assert.equal(policy.active, false);
  assert.deepEqual(policy.blockedDomains, []);
  assert.deepEqual(policy.blockedApps, []);
});

test('expired and consumed enrollment claims cannot be exchanged twice', async t => {
  let consumed = false;
  const now = Date.now();
  t.mock.method(Claim, 'findOneAndUpdate', async query => {
    assert.equal(query.consumedAt, null);
    assert.ok(query.expiresAt.$gt instanceof Date);
    if (consumed || now > expiry) return null;
    consumed = true;
    return { studentId: 'student-a' };
  });
  t.mock.method(Device, 'create', async record => ({ ...record, _id: 'aaaaaaaaaaaaaaaaaaaaaaaa' }));
  const claim = crypto.randomBytes(24).toString('base64url');
  let expiry = now + 60_000;
  const first = response();
  await enrollDevice({ body: { claim }, headers: {} }, first);
  assert.equal(first.code, 201);
  assert.match(first.body.data.credential, /^aaaaaaaaaaaaaaaaaaaaaaaa\./);
  assert.equal(first.body.data.credential.includes(first.body.data.claim || 'impossible'), false);
  const replay = response();
  await enrollDevice({ body: { claim }, headers: {} }, replay);
  assert.equal(replay.code, 400);
  consumed = false;
  expiry = now - 1;
  const expired = response();
  await enrollDevice({ body: { claim: crypto.randomBytes(24).toString('base64url') }, headers: {} }, expired);
  assert.equal(expired.code, 400);
});

test('browser-origin enrollment cannot receive a device credential', async () => {
  const res = response();
  await enrollDevice({ body: { claim: crypto.randomBytes(24).toString('base64url') }, headers: { origin: 'https://example.edu' } }, res);
  assert.equal(res.code, 403);
  assert.equal(res.body?.data?.credential, undefined);
});

test('room authorization allows only owning professor, keeping peer telemetry private', async t => {
  t.mock.method(Session, 'findById', () => ({ select: async () => ({ professorId: 'prof-a', batchIds: ['batch-a'], joinedStudentIds: ['student-a'] }) }));
  assert.equal(await authorizeSessionRoom({ role: 'professor', id: 'prof-a' }, 'aaaaaaaaaaaaaaaaaaaaaaaa'), true);
  assert.equal(await authorizeSessionRoom({ role: 'professor', id: 'prof-b' }, 'aaaaaaaaaaaaaaaaaaaaaaaa'), false);
  assert.equal(await authorizeSessionRoom({ role: 'student', id: 'student-b' }, 'aaaaaaaaaaaaaaaaaaaaaaaa'), false);
  assert.equal(await authorizeSessionRoom({ role: 'student', id: 'student-a' }, 'aaaaaaaaaaaaaaaaaaaaaaaa'), false);
});

test('student cannot join a session outside their batch', async t => {
  const now = Date.now();
  t.mock.method(Session, 'findById', () => ({ select: async () => ({
    _id: 'aaaaaaaaaaaaaaaaaaaaaaaa', status: 'Active',
    startTime: new Date(now - 60_000), endTime: new Date(now + 60_000),
    batchIds: ['batch-a'], joinedStudentIds: [],
  }) }));
  t.mock.method(Student, 'findById', () => ({ select: async () => ({ joinedBatches: ['batch-b'] }) }));
  const res = response();
  await joinSession({ params: { id: 'aaaaaaaaaaaaaaaaaaaaaaaa' }, user: { id: 'student-b' } }, res);
  assert.equal(res.code, 403);
});

test('session clock starts and ends by backend time, idempotently', async t => {
  const now = new Date();
  let started = false;
  let ended = false;
  t.mock.method(Session, 'find', query => ({ select: async () => {
    if (query.status === 'Upcoming') return started ? [] : [{ _id: 'start' }];
    return ended ? [] : [{ _id: 'end' }];
  } }));
  t.mock.method(Session, 'updateOne', async query => {
    if (String(query._id) === 'start' && !started) { started = true; return { modifiedCount: 1 }; }
    if (String(query._id) === 'end' && !ended) { ended = true; return { modifiedCount: 1 }; }
    return { modifiedCount: 0 };
  });
  assert.deepEqual(await clock.reconcileSessions(now), { started: 1, ended: 1 });
  assert.deepEqual(await clock.reconcileSessions(now), { started: 0, ended: 0 });
});

test('Socket.IO rejects unauthenticated connections and arbitrary rooms', async t => {
  process.env.JWT_SECRET = 'test-only-secret-not-for-production';
  const server = http.createServer();
  const io = new Server(server, { cors: { origin: '*' } });
  setupSocket(io);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => io.close(resolve)); server.close(); });
  const url = `http://127.0.0.1:${server.address().port}`;
  const missing = connect(url, { forceNew: true, reconnection: false });
  const error = await new Promise(resolve => missing.on('connect_error', resolve));
  assert.match(error.message, /authentication/i);
  missing.close();
  t.mock.method(Professor, 'exists', async () => true);
  t.mock.method(Session, 'findById', () => ({ select: async () => ({ professorId: 'prof-a', batchIds: [], joinedStudentIds: [] }) }));
  const token = jwt.sign({ id: 'prof-b', role: 'professor' }, process.env.JWT_SECRET, { expiresIn: '1m' });
  const client = connect(url, { forceNew: true, reconnection: false, auth: { token } });
  await new Promise(resolve => client.on('connect', resolve));
  const denied = new Promise(resolve => client.on('authorization_error', resolve));
  client.emit('join_session', 'aaaaaaaaaaaaaaaaaaaaaaaa');
  assert.equal((await denied).room, 'session');
  client.close();
});
