const http = require('http');
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve('C:/workspace/pea');
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/generate-button-preview.html';
  let fp = path.normalize(path.join(ROOT, p));
  if (!fp.startsWith(ROOT)) { res.writeHead(403); res.end('forbidden'); return; }
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found: ' + p); return; }
    const ext = path.extname(fp).toLowerCase();
    const mime = {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'application/javascript','.png':'image/png','.svg':'image/svg+xml','.json':'application/json'}[ext] || 'text/plain';
    res.writeHead(200, {'Content-Type': mime, 'Cache-Control':'no-cache'});
    res.end(data);
  });
});
server.listen(7777, '127.0.0.1', () => console.log('preview server on 7777'));
