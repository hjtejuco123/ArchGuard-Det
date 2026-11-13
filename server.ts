import express from 'express';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const execFileAsync = promisify(execFile);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_BRIDGE_SCRIPT = path.join(__dirname, 'archguard-det', 'app.py');

async function callPythonBridge(command: string, payload: Record<string, unknown> = {}): Promise<any> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      'python3',
      [PYTHON_BRIDGE_SCRIPT, '--bridge', command],
      {
        cwd: __dirname,
        env: {
          ...process.env,
          FLASK_PORT: process.env.FLASK_PORT || '5000',
          ARCHGUARD_DB_PATH: process.env.ARCHGUARD_DB_PATH || path.join(__dirname, 'archguard-det', 'audit_benchmarks.db'),
        },
        maxBuffer: 25 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        const trimmed = stdout.trim();
        if (trimmed) {
          try {
            const parsed = JSON.parse(trimmed);
            if (parsed.error) {
              return reject(new Error(parsed.error));
            }
            return resolve(parsed);
          } catch {
            // Fall through to error handling
          }
        }
        if (error) {
          return reject(new Error(stderr.trim() || error.message));
        }
        return reject(new Error('Empty response from Python bridge'));
      }
    );
    child.stdin?.write(JSON.stringify(payload));
    child.stdin?.end();
  });
}

async function startServer() {
  const app = express();
  app.use(express.json({ limit: '25mb' }));

  app.get('/api/rules', async (_req, res) => {
    try {
      const data = await callPythonBridge('rules_load');
      res.json(data);
    } catch (err: any) {
      res.status(400).json({ error: err?.message || 'Failed to load rules' });
    }
  });

  app.post('/api/rules', async (req, res) => {
    try {
      const { action, yaml_text } = req.body || {};
      const cmd = action === 'save' || typeof yaml_text === 'string' ? 'rules_save' : 'rules_load';
      const data = await callPythonBridge(cmd, { yaml_text });
      res.json(data);
    } catch (err: any) {
      res.status(400).json({ error: err?.message || 'Failed to update rules' });
    }
  });

  app.post('/api/audit', async (req, res) => {
    try {
      const { repo_path, rules_yaml, zip_base64 } = req.body || {};
      const data = await callPythonBridge('audit', { repo_path, rules_yaml, zip_base64 });
      res.json(data);
    } catch (err: any) {
      res.status(400).json({ error: err?.message || 'Audit execution failed' });
    }
  });

  app.post('/api/benchmark/run', async (req, res) => {
    try {
      const { rules_yaml } = req.body || {};
      const data = await callPythonBridge('benchmark', { rules_yaml });
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'Benchmark execution failed' });
    }
  });

  app.get('/api/export/csv', async (_req, res) => {
    try {
      const data = await callPythonBridge('export_csv');
      res.setHeader('Content-Type', 'text/csv; charset=utf-8');
      res.setHeader('Content-Disposition', 'attachment; filename="benchmark_results.csv"');
      res.send(data.content);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'CSV export failed' });
    }
  });

  app.get('/api/export/latex', async (_req, res) => {
    try {
      const data = await callPythonBridge('export_latex');
      res.setHeader('Content-Type', 'application/x-tex; charset=utf-8');
      res.setHeader('Content-Disposition', 'attachment; filename="results_table.tex"');
      res.send(data.content);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'LaTeX export failed' });
    }
  });

  app.get('/api/history', async (_req, res) => {
    try {
      const data = await callPythonBridge('history');
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'History lookup failed' });
    }
  });

  app.get('/api/adi-trend', async (req, res) => {
    try {
      const rawLimit = Number(req.query.limit ?? 50);
      const limit = Number.isFinite(rawLimit) ? Math.max(1, Math.min(200, Math.floor(rawLimit))) : 50;
      const data = await callPythonBridge('adi_trend', { limit });
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'ADI trend lookup failed' });
    }
  });

  const distPath = path.join(__dirname, 'dist');
  const isProd = process.env.NODE_ENV === 'production' && fs.existsSync(distPath);

  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const port = 3000;
  app.listen(port, '0.0.0.0', () => {
    console.log(`ArchGuard-Det workbench listening on http://0.0.0.0:${port}`);
  });
}

void execFileAsync;
startServer();
