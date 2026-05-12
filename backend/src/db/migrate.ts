// ─────────────────────────────────────────────
// 数据库迁移 — 执行 contract/db-schema.sql
// 每条 SQL 语句使用独立 SAVEPOINT，部分失败不影响其余语句
// ─────────────────────────────────────────────

import fs from 'fs';
import path from 'path';
import pool from './pool';

/**
 * 按语句拆分 SQL，正确处理：
 *  - $$...$$ 美元引号块（PL/pgSQL 函数体）
 *  - '...' 单引号字符串（内含分号不拆分，'' 为转义单引号）
 */
function splitSqlStatements(sql: string): string[] {
  const statements: string[] = [];
  let current = '';
  let inDollarQuote = false;
  let dollarTag = '';
  let inSingleQuote = false;
  let i = 0;

  while (i < sql.length) {
    const ch = sql[i];

    // ── 单引号字符串处理 '...' ──────────────────
    if (ch === "'" && !inDollarQuote) {
      if (inSingleQuote) {
        // SQL 转义单引号：'' → 继续留在字符串内
        if (i + 1 < sql.length && sql[i + 1] === "'") {
          current += "''";
          i += 2;
          continue;
        }
        // 普通结束引号
        inSingleQuote = false;
      } else {
        inSingleQuote = true;
      }
      current += ch;
      i++;
      continue;
    }

    // ── 美元引号块处理 $$...$$ ──────────────────
    if (ch === '$' && !inSingleQuote) {
      const end = sql.indexOf('$', i + 1);
      if (end !== -1) {
        const tag = sql.slice(i, end + 1); // e.g. "$$" or "$BODY$"
        if (!inDollarQuote) {
          inDollarQuote = true;
          dollarTag = tag;
          current += tag;
          i = end + 1;
          continue;
        } else if (tag === dollarTag) {
          inDollarQuote = false;
          dollarTag = '';
          current += tag;
          i = end + 1;
          continue;
        }
      }
    }

    // ── 语句分隔符 ──────────────────────────────
    if (ch === ';' && !inDollarQuote && !inSingleQuote) {
      const trimmed = current.trim();
      if (trimmed.length > 0 && !trimmed.startsWith('--')) {
        statements.push(trimmed);
      }
      current = '';
      i++;
      continue;
    }

    current += ch;
    i++;
  }

  // 最后一段（无尾部分号）
  const trimmed = current.trim();
  if (trimmed.length > 0 && !trimmed.startsWith('--')) {
    statements.push(trimmed);
  }

  return statements;
}

/**
 * 读取并执行数据库 schema 文件
 * 幂等：使用 IF NOT EXISTS / OR REPLACE 确保可重复执行
 * 每条语句独立 SAVEPOINT，已存在的对象跳过不报错
 */
export async function runMigrations(): Promise<void> {
  // 优先查找生产部署路径（dist 同目录），其次本地开发路径
  const candidates = [
    path.resolve(__dirname, 'db-schema.sql'),
    path.resolve(__dirname, '..', 'db-schema.sql'),
    path.resolve(__dirname, '..', '..', '..', 'contract', 'db-schema.sql'),
  ];

  let schemaPath: string | null = null;
  for (const p of candidates) {
    if (fs.existsSync(p)) { schemaPath = p; break; }
  }

  if (!schemaPath) {
    console.warn('[Migrate] Schema file not found. Searched:', candidates);
    console.warn('[Migrate] Skipping migrations.');
    return;
  }

  console.log('[Migrate] Reading schema from:', schemaPath);

  const sql = fs.readFileSync(schemaPath, 'utf-8');

  // 按 ; 拆分语句，但正确处理 $$...$$ 美元引号块（PL/pgSQL 函数体）
  // 避免把函数体内的 ; 当作语句分隔符
  const statements = splitSqlStatements(sql);

  console.log(`[Migrate] Found ${statements.length} SQL statements to execute`);

  const client = await pool.connect();
  let applied = 0;
  let skipped = 0;
  let failed  = 0;

  try {
    // 开启外层事务（保证每个 SAVEPOINT 有事务上下文）
    await client.query('BEGIN');

    for (let i = 0; i < statements.length; i++) {
      const stmt = statements[i];
      const spName = `sp_migrate_${i}`;

      await client.query(`SAVEPOINT ${spName}`);

      try {
        await client.query(stmt);
        await client.query(`RELEASE SAVEPOINT ${spName}`);
        applied++;
      } catch (err: any) {
        // 回滚到本语句的 savepoint，让事务继续
        await client.query(`ROLLBACK TO SAVEPOINT ${spName}`);
        await client.query(`RELEASE SAVEPOINT ${spName}`);

        const msg = err.message || '';
        const isIdempotent =
          msg.includes('already exists') ||
          msg.includes('duplicate key') ||
          msg.includes('unique constraint') ||
          msg.includes('does not exist') ||
          msg.includes('violates');

        if (isIdempotent) {
          console.log(`[Migrate] Statement ${i + 1}: skipped (${msg.substring(0, 80)})`);
          skipped++;
        } else {
          console.error(
            `[Migrate] Statement ${i + 1} FAILED: ${msg.substring(0, 200)}`
          );
          console.error(
            `[Migrate] Statement preview: ${stmt.substring(0, 200)}`
          );
          failed++;
          // 非幂等错误：继续执行其余语句，但记录失败数
        }
      }
    }

    await client.query('COMMIT');
    console.log(
      `[Migrate] Done — applied=${applied}, skipped=${skipped}, failed=${failed}`
    );

    if (failed > 0) {
      console.warn(
        `[Migrate] ${failed} statement(s) failed with unexpected errors. ` +
        `Run 'psql seedance < contract/db-schema.sql' to inspect manually.`
      );
    }
  } catch (err) {
    await client.query('ROLLBACK');
    const message = err instanceof Error ? err.message : String(err);
    console.error('[Migrate] Fatal error, rolled back entire migration:', message);
    throw err;
  } finally {
    client.release();
  }
}

/**
 * 作为独立脚本运行时执行迁移
 */
if (require.main === module) {
  runMigrations()
    .then(() => {
      console.log('[Migrate] Done.');
      process.exit(0);
    })
    .catch((err) => {
      console.error('[Migrate] Fatal:', err);
      process.exit(1);
    });
}
