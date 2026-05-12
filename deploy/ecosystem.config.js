// ─────────────────────────────────────────────
// PM2 Ecosystem — Seedance Wizard 生产配置
//
// 用法：
//   pm2 start ecosystem.config.js
//   pm2 save
//   pm2 startup   # 开机自启
// ─────────────────────────────────────────────

module.exports = {
  apps: [
    // ── 后端 Node.js API ──────────────────────
    {
      name: 'seedance-backend',
      cwd:  '/var/www/seedance/backend',
      script: 'dist/server.js',           // npm run build 后的产物
      interpreter: 'node',
      instances: 1,                        // 单实例（DB 连接池管理更简单）
      exec_mode: 'fork',

      // 环境变量（生产）
      env: {
        NODE_ENV:           'production',
        PORT:               '3000',
        DEPLOYMENT_REGION:  'cn',
        // 其余变量从 /var/www/seedance/backend/.env 加载（dotenv）
      },

      // 进程守护
      watch:           false,
      max_memory_restart: '512M',
      restart_delay:   3000,
      max_restarts:    10,

      // 日志
      out_file:  '/var/log/pm2/seedance-backend-out.log',
      error_file:'/var/log/pm2/seedance-backend-err.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },

    // ── 前端 Next.js ──────────────────────────
    {
      name: 'seedance-frontend',
      cwd:  '/var/www/seedance/web-portal',
      script: 'node_modules/.bin/next',
      args:   'start -p 3001',
      interpreter: 'node',
      instances: 1,
      exec_mode: 'fork',

      env: {
        NODE_ENV:                 'production',
        PORT:                     '3001',
        NEXT_PUBLIC_API_BASE_URL: '',  // 同域，Nginx 代理，留空即可
      },

      watch:              false,
      max_memory_restart: '512M',
      restart_delay:      3000,
      max_restarts:       10,

      out_file:  '/var/log/pm2/seedance-frontend-out.log',
      error_file:'/var/log/pm2/seedance-frontend-err.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },
  ],
};
