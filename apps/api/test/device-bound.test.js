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
const Batch = require('../dist/models/Batch').default;
const Claim = require('../dist/models/EnrollmentClaim').default;
const Otp = require('../dist/models/Otp').default;
const ActivityEvent = require('../dist/models/ActivityEvent').default;
const { aggregateSessionData } = require('../dist/utils/sessionAnalytics');
const { generateSessionSummary } = require('../dist/utils/geminiSummary');
const { requestOtp, createStudentProfile } = require('../dist/controllers/authController');
const clock = require('../dist/services/sessionClock');
const { authenticateDevice, deviceAuth, hashCredential } = require('../dist/middleware/deviceAuth');
const { policyForDevice } = require('../dist/services/devicePolicy');
const { enrollDevice } = require('../dist/controllers/enrollmentController');
const { createSession, joinSession, getSessionCoverage, getSessionSummary } = require('../dist/controllers/sessionController');
const { authorize } = require('../dist/middleware/auth');
const { classifyCoverage, FRESH_MS } = require('../dist/services/sessionCoverage');
const { createRule } = require('../dist/controllers/ruleController');
const { authorizeSessionRoom, setupSocket } = require('../dist/services/socketService');
const logRoutes = require('../dist/routes/logRoutes').default;
const app = require('../dist/app').default;

function response() {
  return { code: 200, body: null, status(code) { this.code = code; return this; }, json(body) { this.body = body; return this; } };
}

test('session summary does not treat missing agent telemetry as focus', async t => {
  const sessionId = 'aaaaaaaaaaaaaaaaaaaaaaaa';
  t.mock.method(Session, 'findById', () => ({ select: async () => ({
    title: 'Test Lab', startTime: new Date(0), endTime: new Date(60 * 60 * 1000),
    batchIds: ['batch-a'], joinedStudentIds: ['student-a'],
  }) }));
  t.mock.method(Batch, 'find', () => ({ select: () => ({ lean: async () => [{ students: ['student-a', 'student-b'] }] }) }));
  t.mock.method(ActivityEvent, 'aggregate', async () => []);
  const data = await aggregateSessionData(sessionId);
  assert.equal(data.totalStudents, 2);
  assert.equal(data.observedStudents, 0);
  assert.equal(data.unobservedStudents, 2);
  assert.equal(data.focusedCount, 0);
  const previousKey = process.env.GEMINI_API_KEY;
  delete process.env.GEMINI_API_KEY;
  t.after(() => { if (previousKey === undefined) delete process.env.GEMINI_API_KEY; else process.env.GEMINI_API_KEY = previousKey; });
  const summary = await generateSessionSummary(data);
  assert.match(summary, /no agent activity was recorded/i);
  assert.match(summary, /no conclusions about student focus/i);
});

test('session summary rejects active sessions before generating or caching', async t => {
  t.mock.method(clock, 'reconcileSessions', async () => ({ started: 0, ended: 0 }));
  t.mock.method(Session, 'findById', () => ({ select: async () => ({ professorId: 'prof-a', status: 'Active' }) }));
  const res = response();
  await getSessionSummary({ params: { id: 'aaaaaaaaaaaaaaaaaaaaaaaa' }, user: { id: 'prof-a', role: 'professor' } }, res);
  assert.equal(res.code, 409);
});

test('legacy cached summary is replaced with a factual no-telemetry report', async t => {
  t.mock.method(clock, 'reconcileSessions', async () => ({ started: 0, ended: 0 }));
  t.mock.method(Session, 'findById', () => ({ select: async fields => fields.includes('summaryVersion')
    ? { professorId: 'prof-a', status: 'Completed', aiSummary: 'All students focused', summaryVersion: undefined }
    : { title: 'Test Lab', startTime: new Date(0), endTime: new Date(60 * 60 * 1000), batchIds: [], joinedStudentIds: ['student-a'] } }));
  t.mock.method(ActivityEvent, 'aggregate', async () => []);
  let replacement;
  t.mock.method(Session, 'updateOne', async (_query, update) => { replacement = update.$set; return { modifiedCount: 1 }; });
  const res = response();
  await getSessionSummary({ params: { id: 'aaaaaaaaaaaaaaaaaaaaaaaa' }, user: { id: 'prof-a', role: 'professor' } }, res);
  assert.equal(res.code, 200);
  assert.match(res.body.data.aiSummary, /no agent activity was recorded/i);
  assert.equal(replacement.summaryVersion, 2);
});

test('desktop app origin is allowed without accepting arbitrary local origins', async t => {
  const previousMode = process.env.NODE_ENV;
  process.env.NODE_ENV = 'production';
  t.after(() => { if (previousMode === undefined) delete process.env.NODE_ENV; else process.env.NODE_ENV = previousMode; });
  const server = http.createServer(app);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  const check = origin => new Promise((resolve, reject) => {
    const request = http.get({ hostname: '127.0.0.1', port: server.address().port, path: '/', headers: { Origin: origin } }, result => {
      result.resume();
      result.on('end', () => resolve(result.headers['access-control-allow-origin']));
    });
    request.on('error', reject);
  });
  assert.equal(await check('academia://academia-shield'), 'academia://academia-shield');
  assert.equal(await check('academia://untrusted'), undefined);
});

test('coverage classifies batch members and attendance without revoked devices', () => {
  const now = new Date();
  const session = { _id: 'session-a', joinedStudentIds: ['student-b'] };
  const batches = [{ students: ['student-a', 'student-b'] }, { students: ['student-c', 'student-a'] }];
  const students = ['student-a', 'student-b', 'student-c'].map(_id => ({ _id, name: _id }));
  const devices = [
    { studentId: 'student-a', lastSeenAt: new Date(now.getTime() - FRESH_MS + 1) },
    { studentId: 'student-b', lastSeenAt: new Date(now.getTime() - FRESH_MS - 1) },
  ];
  const result = classifyCoverage(session, batches, students, devices, now);
  assert.deepEqual(result.students.map(student => [student.studentId, student.status, student.joined]), [
    ['student-a', 'active', false], ['student-b', 'enrolled_silent', true], ['student-c', 'not_enrolled', false],
  ]);
  assert.deepEqual(result.summary, { total: 3, active: 1, enrolled_silent: 1, not_enrolled: 1, joined: 1 });
});

test('coverage route rejects non-owner professors and student roles', async t => {
  t.mock.method(Session, 'findById', () => ({ select: () => ({ lean: async () => ({
    _id: 'aaaaaaaaaaaaaaaaaaaaaaaa', professorId: 'prof-a', batchIds: [], joinedStudentIds: [],
  }) }) }));
  const nonOwner = response();
  await getSessionCoverage({ params: { id: 'aaaaaaaaaaaaaaaaaaaaaaaa' }, user: { id: 'prof-b', role: 'professor' } }, nonOwner);
  assert.equal(nonOwner.code, 403);
  const student = response();
  authorize('professor')({ user: { id: 'student-a', role: 'student' } }, student, () => { throw new Error('student passed'); });
  assert.equal(student.code, 403);
});

test('coverage lookup excludes revoked devices with grouped queries', async t => {
  const { loadCoverages } = require('../dist/services/sessionCoverage');
  t.mock.method(Batch, 'find', () => ({ select: () => ({ lean: async () => [{ _id: 'batch-a', students: ['student-a'] }] }) }));
  t.mock.method(Student, 'find', () => ({ select: () => ({ lean: async () => [{ _id: 'student-a' }] }) }));
  t.mock.method(Device, 'find', query => {
    assert.equal(query.revokedAt, null);
    return { select: () => ({ lean: async () => [] }) };
  });
  const [coverage] = await loadCoverages([{ _id: 'session-a', batchIds: ['batch-a'], joinedStudentIds: [] }]);
  assert.equal(coverage.summary.not_enrolled, 1);
});

test('student socket cannot receive session coverage', async t => {
  process.env.JWT_SECRET = 'test-only-secret-not-for-production';
  const server = http.createServer();
  const io = new Server(server, { cors: { origin: '*' } });
  setupSocket(io);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => io.close(resolve)); server.close(); });
  t.mock.method(Student, 'exists', async () => true);
  t.mock.method(Session, 'findById', () => ({ select: async () => ({ professorId: 'prof-a' }) }));
  const token = jwt.sign({ id: 'student-a', role: 'student' }, process.env.JWT_SECRET, { expiresIn: '1m' });
  const client = connect(`http://127.0.0.1:${server.address().port}`, { forceNew: true, reconnection: false, auth: { token } });
  await new Promise(resolve => client.on('connect', resolve));
  let received = false;
  client.on('session_coverage', () => { received = true; });
  const denied = new Promise(resolve => client.once('authorization_error', resolve));
  client.emit('join_session', 'aaaaaaaaaaaaaaaaaaaaaaaa');
  assert.equal((await denied).room, 'session');
  io.to('aaaaaaaaaaaaaaaaaaaaaaaa').emit('session_coverage', { summary: { active: 1 } });
  await new Promise(resolve => setTimeout(resolve, 50));
  assert.equal(received, false);
  client.close();
});

test('OTP is never returned when DEMO_MODE is off', async t => {
  t.mock.method(Otp, 'findOne', () => ({ sort: async () => null }));
  t.mock.method(Otp, 'deleteMany', async () => ({}));
  t.mock.method(Otp, 'create', async () => ({}));
  const prior = { DEMO_MODE: process.env.DEMO_MODE, EMAIL_USER: process.env.EMAIL_USER, EMAIL_PASS: process.env.EMAIL_PASS, EMAIL_SERVICE: process.env.EMAIL_SERVICE, STUDENT_EMAIL_DOMAIN: process.env.STUDENT_EMAIL_DOMAIN };
  process.env.DEMO_MODE = 'false';
  process.env.EMAIL_USER = 'test@example.invalid';
  process.env.EMAIL_PASS = 'synthetic-test-value';
  process.env.EMAIL_SERVICE = 'synthetic';
  process.env.STUDENT_EMAIL_DOMAIN = 'university.example';
  t.mock.method(Student, 'findOne', () => ({ select: async () => null }));
  const email = require('../dist/utils/email');
  t.mock.method(email, 'sendEmail', async () => undefined);
  try {
    const res = response();
    await requestOtp({ body: { sapId: '12345678901' } }, res);
    assert.equal(res.code, 200);
    assert.equal(JSON.stringify(res.body).includes('mockOtp'), false);
    assert.equal(res.body.data.otpMode, 'email');
    assert.equal(Object.hasOwn(res.body.data, 'otp'), false);
  } finally {
    for (const [key, value] of Object.entries(prior)) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
});

test('student OTP rejects SAP IDs that are not exactly 11 digits', async () => {
  const res = response();
  await requestOtp({ body: { sapId: '123456789012' } }, res);
  assert.equal(res.code, 400);
  assert.match(res.body.message, /exactly 11 digits/i);
});

test('failed SMTP never falls back to a returned mock OTP', async t => {
  t.mock.method(Otp, 'findOne', () => ({ sort: async () => null }));
  t.mock.method(Otp, 'deleteMany', async () => ({}));
  t.mock.method(Otp, 'create', async () => ({}));
  const prior = { DEMO_MODE: process.env.DEMO_MODE, EMAIL_USER: process.env.EMAIL_USER, EMAIL_PASS: process.env.EMAIL_PASS, EMAIL_SERVICE: process.env.EMAIL_SERVICE, STUDENT_EMAIL_DOMAIN: process.env.STUDENT_EMAIL_DOMAIN };
  process.env.DEMO_MODE = 'false';
  process.env.EMAIL_USER = 'test@example.invalid';
  process.env.EMAIL_PASS = 'synthetic-test-value';
  process.env.EMAIL_SERVICE = 'synthetic';
  process.env.STUDENT_EMAIL_DOMAIN = 'university.example';
  t.mock.method(Student, 'findOne', () => ({ select: async () => null }));
  const email = require('../dist/utils/email');
  t.mock.method(email, 'sendEmail', async () => { throw new Error('synthetic delivery failure'); });
  try {
    const res = response();
    await requestOtp({ body: { sapId: '12345678901' } }, res);
    assert.equal(res.code, 502);
    assert.equal(JSON.stringify(res.body).includes('mockOtp'), false);
  } finally {
    for (const [key, value] of Object.entries(prior)) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
});

test('OTP request returns 503 without SMTP when DEMO_MODE is off', async t => {
  t.mock.method(Otp, 'findOne', () => ({ sort: async () => null }));
  const prior = { DEMO_MODE: process.env.DEMO_MODE, EMAIL_USER: process.env.EMAIL_USER, EMAIL_PASS: process.env.EMAIL_PASS, EMAIL_SERVICE: process.env.EMAIL_SERVICE };
  delete process.env.DEMO_MODE;
  delete process.env.EMAIL_USER;
  delete process.env.EMAIL_PASS;
  delete process.env.EMAIL_SERVICE;
  try {
    const res = response();
    await requestOtp({ body: { sapId: '12345678901' } }, res);
    assert.equal(res.code, 503);
    assert.equal(JSON.stringify(res.body).includes('mockOtp'), false);
  } finally {
    for (const [key, value] of Object.entries(prior)) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
});

test('new student OTP refuses an unknown email mapping without creating a code', async t => {
  const prior = { DEMO_MODE: process.env.DEMO_MODE, EMAIL_USER: process.env.EMAIL_USER, EMAIL_PASS: process.env.EMAIL_PASS, EMAIL_SERVICE: process.env.EMAIL_SERVICE, STUDENT_EMAIL_DOMAIN: process.env.STUDENT_EMAIL_DOMAIN };
  process.env.DEMO_MODE = 'false';
  process.env.EMAIL_USER = 'test@example.invalid';
  process.env.EMAIL_PASS = 'synthetic-test-value';
  process.env.EMAIL_SERVICE = 'synthetic';
  delete process.env.STUDENT_EMAIL_DOMAIN;
  t.after(() => { for (const [key, value] of Object.entries(prior)) value === undefined ? delete process.env[key] : process.env[key] = value; });
  t.mock.method(Otp, 'findOne', () => ({ sort: async () => null }));
  t.mock.method(Student, 'findOne', () => ({ select: async () => null }));
  t.mock.method(Otp, 'create', async () => { throw new Error('No OTP must be created'); });
  const res = response();
  await requestOtp({ body: { sapId: '12345678901' } }, res);
  assert.equal(res.code, 503);
  assert.equal(JSON.stringify(res.body).includes('mockOtp'), false);
});

test('existing student OTP is delivered to the stored address', async t => {
  const prior = { DEMO_MODE: process.env.DEMO_MODE, EMAIL_USER: process.env.EMAIL_USER, EMAIL_PASS: process.env.EMAIL_PASS, EMAIL_SERVICE: process.env.EMAIL_SERVICE, STUDENT_EMAIL_DOMAIN: process.env.STUDENT_EMAIL_DOMAIN };
  process.env.DEMO_MODE = 'false';
  process.env.EMAIL_USER = 'sender@example.invalid';
  process.env.EMAIL_PASS = 'synthetic-test-value';
  process.env.EMAIL_SERVICE = 'synthetic';
  delete process.env.STUDENT_EMAIL_DOMAIN;
  t.after(() => { for (const [key, value] of Object.entries(prior)) value === undefined ? delete process.env[key] : process.env[key] = value; });
  t.mock.method(Otp, 'findOne', () => ({ sort: async () => null }));
  t.mock.method(Otp, 'deleteMany', async () => ({}));
  t.mock.method(Otp, 'create', async () => ({}));
  t.mock.method(Student, 'findOne', () => ({ select: async () => ({ email: 'registered@university.example' }) }));
  const email = require('../dist/utils/email');
  let destination;
  t.mock.method(email, 'sendEmail', async to => { destination = to; });
  const res = response();
  await requestOtp({ body: { sapId: '12345678901' } }, res);
  assert.equal(res.code, 200);
  assert.equal(destination, 'registered@university.example');
  assert.equal(JSON.stringify(res.body).includes('registered@university.example'), false);
});

test('student profile cannot replace its verified email with a supplied address', async () => {
  const res = response();
  await createStudentProfile({ user: { id: '12345678901', role: 'student_temp', email: 'verified@university.example' }, body: {
    sapId: '12345678901', name: 'Student', email: 'attacker@example.invalid', department: 'CE', rollNumber: '1', year: '1',
  } }, res);
  assert.equal(res.code, 403);
});

test('new profile stores only the OTP-verified address from the signed session', async t => {
  const previousSecret = process.env.JWT_SECRET;
  process.env.JWT_SECRET = 'synthetic-test-only-secret';
  t.after(() => { if (previousSecret === undefined) delete process.env.JWT_SECRET; else process.env.JWT_SECRET = previousSecret; });
  t.mock.method(Student, 'findOne', async () => null);
  let created;
  t.mock.method(Student, 'create', async payload => { created = payload; return { ...payload, _id: 'student-a' }; });
  t.mock.method(Otp, 'deleteMany', async () => ({}));
  const res = response();
  await createStudentProfile({ user: { id: '12345678901', role: 'student_temp', email: 'verified@university.example' }, body: {
    sapId: '12345678901', name: 'Student', department: 'CE', rollNumber: '1', year: '1',
  } }, res);
  assert.equal(res.code, 201);
  assert.equal(created.email, 'verified@university.example');
});

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
    const sid = String(query.$or[1].joinedStudentIds);
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
  assert.equal(seen[0].$or[1].joinedStudentIds, 'student-a');
  assert.deepEqual(seen[1].batchIds.$in, ['batch-b']);
  assert.ok(new Date(a.expiresAt) <= new Date(a.active_sessions[0].ends_at));
  await assert.rejects(() => policyForDevice({ _id: 'revoked', studentId: 'student-a', revokedAt: new Date() }), /revoked/);
});

async function policyWithSessions(t, { joinedBatches = ['batch-a'], sessions = [], revokedAt = null, now = new Date() }) {
  t.mock.method(clock, 'reconcileSessions', async () => ({ started: 0, ended: 0 }));
  t.mock.method(Student, 'findById', () => ({ select: async () => ({ joinedBatches }) }));
  t.mock.method(Session, 'find', query => ({ select: async () => sessions.filter(session =>
    session.status === query.status &&
    session.startTime <= query.startTime.$lte && session.endTime > query.endTime.$gt &&
    session.batchIds.some(id => query.batchIds.$in.includes(id)) &&
    (session.joinMode === 'auto' || session.joinedStudentIds.includes(query.$or[1].joinedStudentIds))
  ) }));
  t.mock.method(Rule, 'findOne', async () => ({ websites: ['blocked.example'], applications: [] }));
  return policyForDevice({ _id: 'device-a', studentId: 'student-a', revokedAt }, now);
}

function labSession(overrides = {}) {
  const now = Date.now();
  return {
    _id: 'session-a', title: 'Lab', status: 'Active', joinMode: 'auto',
    startTime: new Date(now - 60_000), endTime: new Date(now + 60_000),
    professorId: 'prof-a', ruleSetId: 'rule-a', batchIds: ['batch-a'],
    joinedStudentIds: [], ...overrides,
  };
}

test('auto session gives an enrolled batch member policy without attendance join', async t => {
  const session = labSession();
  const policy = await policyWithSessions(t, { sessions: [session] });
  assert.equal(policy.active, true);
  assert.deepEqual(policy.blockedDomains, ['blocked.example']);
  assert.ok(new Date(policy.expiresAt) <= session.endTime);
});

test('session creation validates joinMode and defaults to opt-in', async t => {
  const body = {
    title: 'Lab', course: 'Course', type: 'Lab',
    startTime: new Date(Date.now() + 60_000).toISOString(),
    endTime: new Date(Date.now() + 120_000).toISOString(),
    ruleSetId: 'aaaaaaaaaaaaaaaaaaaaaaaa', batchIds: ['bbbbbbbbbbbbbbbbbbbbbbbb'],
  };
  const invalid = response();
  await createSession({ body: { ...body, joinMode: 'other' }, user: { id: 'prof-a' } }, invalid);
  assert.equal(invalid.code, 400);
  const created = [];
  t.mock.method(require('../dist/models/Batch').default, 'countDocuments', async () => 1);
  t.mock.method(Rule, 'exists', async () => true);
  t.mock.method(Session, 'create', async data => { created.push(data); return data; });
  await createSession({ body, user: { id: 'prof-a' } }, response());
  await createSession({ body: { ...body, joinMode: 'auto' }, user: { id: 'prof-a' } }, response());
  assert.deepEqual(created.map(item => item.joinMode), ['opt-in', 'auto']);
});

test('opt-in session without attendance join gives no policy', async t => {
  const policy = await policyWithSessions(t, { sessions: [labSession({ joinMode: 'opt-in' })] });
  assert.equal(policy.active, false);
});

test('student outside session batch gets no automatic policy', async t => {
  const policy = await policyWithSessions(t, { joinedBatches: ['batch-b'], sessions: [labSession()] });
  assert.equal(policy.active, false);
});

test('revoked device gets no automatic policy', async t => {
  await assert.rejects(() => policyWithSessions(t, { sessions: [labSession()], revokedAt: new Date() }), /revoked/);
});

test('expired and future sessions give no automatic policy', async t => {
  const now = new Date();
  const policy = await policyWithSessions(t, { now, sessions: [
    labSession({ endTime: new Date(now.getTime() - 1) }),
    labSession({ startTime: new Date(now.getTime() + 60_000) }),
  ] });
  assert.equal(policy.active, false);
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
