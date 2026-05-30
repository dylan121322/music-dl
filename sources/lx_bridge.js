/**
 * Bridge: runs LX Music JS sources and communicates via stdin/stdout JSON.
 * Usage: node lx_bridge.js <source.js>
 * Input:  JSON lines on stdin  {"action":"search","keyword":"晴天"}
 * Output: JSON lines on stdout {"results":[...]} or {"error":"..."}
 */
const fs = require('fs');
const https = require('https');
const http = require('http');
const { Buffer } = require('buffer');
const crypto = require('crypto');

const sourceFile = process.argv[2];
if (!sourceFile) { process.stderr.write('Usage: node lx_bridge.js <source.js>\n'); process.exit(1); }

// ── Mock globalThis.lx ──
const sourcesDef = {};
let eventHandlers = {};

globalThis.lx = {
  version: '1.0.0',
  env: 'desktop',
  currentScriptInfo: {},
  EVENT_NAMES: {
    request: 'request',
    inited: 'inited',
    updateAlert: 'updateAlert',
  },

  on(event, handler) {
    eventHandlers[event] = handler;
  },

  send(event, data) {
    if (event === 'inited') {
      Object.assign(sourcesDef, data.sources || {});
    }
  },

  request(url, options, callback) {
    const client = url.startsWith('https') ? https : http;
    const u = new URL(url);
    const reqOpts = {
      hostname: u.hostname, port: u.port, path: u.pathname + u.search,
      method: (options.method || 'GET').toUpperCase(),
      headers: options.headers || {},
      timeout: options.timeout || 10000,
    };

    const req = client.request(reqOpts, (res) => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => {
        try { callback(null, { body: JSON.parse(body), statusCode: res.statusCode }); }
        catch (e) { callback(null, { body, statusCode: res.statusCode }); }
      });
    });
    req.on('error', e => callback(e));
    req.on('timeout', () => { req.destroy(); callback(new Error('timeout')); });

    if (options.body) req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    req.end();
  },

  utils: {
    buffer: {
      from: (...args) => Buffer.from(...args),
      bufToString: (buf, enc) => buf.toString(enc || 'utf-8'),
    },
    crypto: {
      aesEncrypt: () => { throw new Error('not implemented'); },
      md5: (data) => crypto.createHash('md5').update(data).digest('hex'),
      randomBytes: (len) => crypto.randomBytes(len).toString('hex'),
      rsaEncrypt: () => { throw new Error('not implemented'); },
    },
    zlib: { inflate: () => { throw new Error('not implemented'); }, deflate: () => { throw new Error('not implemented'); } },
  },
};

// ── Load source ──
try { require(sourceFile); }
catch (e) { process.stderr.write('Load error: ' + e.message + '\n'); process.exit(1); }
process.stderr.write('Source loaded: sources=' + Object.keys(sourcesDef).join(',') + '\n');

// ── Handle commands from stdin ──
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });

rl.on('line', async (line) => {
  try {
    const cmd = JSON.parse(line);
    const handler = eventHandlers['request'];
    if (!handler) { console.log(JSON.stringify({ error: 'No request handler' })); return; }

    let result;
    switch (cmd.action) {
      case 'search': {
        // Try each source's search-like behavior
        const results = [];
        for (const [key, def] of Object.entries(sourcesDef)) {
          try {
            const resp = await handler({ source: key, action: 'musicUrl', info: { type: '320k', musicInfo: { songmid: cmd.keyword, name: cmd.keyword, singer: '' } } });
            if (resp) results.push({ source: key, name: def.name, url: resp });
          } catch (e) {}
        }
        console.log(JSON.stringify({ results }));
        break;
      }
      case 'musicUrl': {
        const resp = await handler({ source: cmd.source, action: 'musicUrl', info: { type: cmd.quality || '320k', musicInfo: cmd.info || {} } });
        console.log(JSON.stringify({ url: resp }));
        break;
      }
      case 'sources':
        console.log(JSON.stringify({ sources: sourcesDef }));
        break;
      default:
        console.log(JSON.stringify({ error: 'Unknown action: ' + cmd.action }));
    }
  } catch (e) {
    console.log(JSON.stringify({ error: e.message }));
  }
});

rl.on('close', () => process.exit(0));
