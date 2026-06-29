import mongoose from 'mongoose';
import dns from 'dns';

const DEFAULT_LOCAL_URI = 'mongodb://localhost:27017/academia-shield';
const DEFAULT_DB_NAME = 'academia-shield';

const RETRY_ATTEMPTS = Number(process.env.MONGO_RETRY_ATTEMPTS || 5);
const RETRY_DELAY_MS = Number(process.env.MONGO_RETRY_DELAY_MS || 2500);

const DNS_SERVERS = (process.env.MONGO_DNS_SERVERS || '8.8.8.8,8.8.4.4,1.1.1.1')
  .split(',')
  .map((server) => server.trim())
  .filter(Boolean);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const maskMongoUri = (uri: string) => {
  try {
    const parsed = new URL(uri);
    if (parsed.password) {
      parsed.password = '***';
    }
    return parsed.toString();
  } catch {
    return uri;
  }
};

const normalizeMongoUri = (rawUri: string) => {
  const uri = rawUri?.trim();
  if (!uri) {
    return DEFAULT_LOCAL_URI;
  }

  try {
    const parsed = new URL(uri);
    const isMongoProtocol = parsed.protocol === 'mongodb:' || parsed.protocol === 'mongodb+srv:';

    if (!isMongoProtocol) {
      return uri;
    }

    if (parsed.pathname === '/' || parsed.pathname === '') {
      parsed.pathname = `/${process.env.MONGO_DB_NAME || DEFAULT_DB_NAME}`;
    }

    return parsed.toString();
  } catch {
    return uri;
  }
};

const buildMongoUriCandidates = () => {
  const primary = normalizeMongoUri(process.env.MONGO_URI || DEFAULT_LOCAL_URI);
  const directRaw = process.env.MONGO_URI_DIRECT?.trim();
  const directFallback = directRaw ? normalizeMongoUri(directRaw) : '';

  return [...new Set([primary, directFallback].filter(Boolean))];
};

let listenersRegistered = false;

const registerConnectionListeners = () => {
  if (listenersRegistered) {
    return;
  }

  listenersRegistered = true;
  mongoose.connection.on('error', (err) => {
    console.error(`[mongo] connection error: ${err.message}`);
  });
  mongoose.connection.on('disconnected', () => {
    console.warn('[mongo] disconnected');
  });
};

export const connectDB = async () => {
  registerConnectionListeners();

  if (DNS_SERVERS.length > 0) {
    dns.setServers(DNS_SERVERS);
  }

  const uriCandidates = buildMongoUriCandidates();
  let lastError: unknown = null;

  for (let attempt = 1; attempt <= RETRY_ATTEMPTS; attempt += 1) {
    for (const uri of uriCandidates) {
      try {
        console.log(
          `[mongo] connect attempt ${attempt}/${RETRY_ATTEMPTS} using ${maskMongoUri(uri)}`
        );

        const conn = await mongoose.connect(uri, {
          serverSelectionTimeoutMS: 10000,
          socketTimeoutMS: 45000,
          maxPoolSize: 10,
          family: 4,
        });

        console.log(
          `✅ MongoDB connected: host=${conn.connection.host} db=${conn.connection.name}`
        );
        return conn;
      } catch (error: any) {
        lastError = error;
        console.error(
          `[mongo] attempt ${attempt} failed for ${maskMongoUri(uri)}: ${error.message}`
        );
      }
    }

    if (attempt < RETRY_ATTEMPTS) {
      console.log(`[mongo] retrying in ${RETRY_DELAY_MS}ms...`);
      await sleep(RETRY_DELAY_MS);
    }
  }

  throw new Error(
    `MongoDB connection failed after ${RETRY_ATTEMPTS} attempts: ${(lastError as any)?.message || 'Unknown error'}`
  );
};