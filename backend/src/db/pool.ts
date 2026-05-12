// ─────────────────────────────────────────────
// PostgreSQL 连接池
// ─────────────────────────────────────────────

import { Pool, PoolClient, QueryResult } from 'pg';
import { config } from '../config';

const pool = new Pool({
  connectionString: config.databaseUrl,
  max: 20, // 最大连接数
  idleTimeoutMillis: 30000, // 空闲连接超时
  connectionTimeoutMillis: 5000, // 连接超时
});

pool.on('error', (err: Error) => {
  console.error('[DB Pool] Unexpected pool error:', err.message);
});

pool.on('connect', () => {
  console.log('[DB Pool] New client connected');
});

/**
 * 测试数据库连接
 */
export async function testConnection(): Promise<boolean> {
  try {
    const client = await pool.connect();
    const result = await client.query('SELECT NOW() AS current_time');
    client.release();
    console.log(
      '[DB] Connection test OK, server time:',
      result.rows[0].current_time
    );
    return true;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('[DB] Connection test FAILED:', message);
    return false;
  }
}

/**
 * 执行查询
 */
export async function query<T extends import('pg').QueryResultRow = any>(
  text: string,
  params?: any[]
): Promise<QueryResult<T>> {
  return pool.query<T>(text, params);
}

/**
 * 获取事务客户端
 */
export async function getClient(): Promise<PoolClient> {
  return pool.connect();
}

/**
 * 在事务中执行操作
 */
export async function transaction<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

/**
 * 关闭连接池
 */
export async function closePool(): Promise<void> {
  await pool.end();
  console.log('[DB Pool] Closed');
}

export default pool;
