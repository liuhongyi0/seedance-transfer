// ─────────────────────────────────────────────
// 统一错误处理中间件
// 确保所有错误都以 { code, message } 格式返回
// ─────────────────────────────────────────────

import { Request, Response, NextFunction } from 'express';

/**
 * 应用层错误类 —— 可预设 HTTP 状态码和错误码
 */
export class AppError extends Error {
  public readonly statusCode: number;
  public readonly code: string;

  constructor(statusCode: number, code: string, message: string) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.name = 'AppError';
  }

  static badRequest(message: string): AppError {
    return new AppError(400, 'BAD_REQUEST', message);
  }

  static unauthorized(message: string = '未授权访问'): AppError {
    return new AppError(401, 'UNAUTHORIZED', message);
  }

  static insufficientBalance(message: string = '余额不足，请充值'): AppError {
    return new AppError(402, 'INSUFFICIENT_BALANCE', message);
  }

  static notFound(message: string = '资源不存在'): AppError {
    return new AppError(404, 'NOT_FOUND', message);
  }

  static conflict(message: string): AppError {
    return new AppError(409, 'CONFLICT', message);
  }

  static tooMany(message: string = '请求过于频繁'): AppError {
    return new AppError(429, 'RATE_LIMITED', message);
  }

  static upstream(message: string = '上游服务异常'): AppError {
    return new AppError(502, 'UPSTREAM_ERROR', message);
  }

  static internal(message: string = '服务器内部错误'): AppError {
    return new AppError(500, 'INTERNAL_ERROR', message);
  }
}

/**
 * 统一错误处理中间件（Express 4 参数签名）
 */
export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  // 记录错误日志
  const requestId = req.requestId || '';
  console.error(
    `[Error] ${requestId} ${req.method} ${req.path}:`,
    err.message
  );

  if (err instanceof AppError) {
    res.status(err.statusCode).json({
      code: err.code,
      message: err.message,
    });
    return;
  }

  // JSON 解析错误
  if (err.name === 'SyntaxError' && 'body' in err) {
    res.status(400).json({
      code: 'INVALID_JSON',
      message: '请求体 JSON 格式错误',
    });
    return;
  }

  // 未知错误
  if (process.env.NODE_ENV === 'production') {
    res.status(500).json({
      code: 'INTERNAL_ERROR',
      message: '服务器内部错误，请稍后重试',
    });
  } else {
    res.status(500).json({
      code: 'INTERNAL_ERROR',
      message: err.message || '服务器内部错误',
    });
  }
}
