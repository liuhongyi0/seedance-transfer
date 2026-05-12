// ─────────────────────────────────────────────
// 邮件发送服务（Resend API）
// 未配置时自动 fallback 到 console mock
// ─────────────────────────────────────────────

import { config } from '../config';

export async function sendVerificationCode(email: string, code: string): Promise<void> {
  if (!config.resendApiKey) {
    console.log(`\n[MAIL Mock] ───────────────────────────────────
  收件人: ${email}
  验证码: ${code}
  有效期: ${config.smsCodeExpiryMs / 1000} 秒
───────────────────────────────────────────\n`);
    return;
  }

  try {
    const resp = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${config.resendApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: config.resendFromEmail || 'Seedance <onboarding@resend.dev>',
        to: [email],
        subject: 'Seedance 验证码 / Verification Code',
        html: `<div style="font-family:sans-serif;max-width:480px;margin:0 auto">
          <h2>Seedance Wizard</h2>
          <p>你的验证码为 / Your verification code:</p>
          <p style="font-size:32px;font-weight:bold;letter-spacing:4px;color:#1a56db">${code}</p>
          <p style="color:#666">5 分钟内有效 / Valid for 5 minutes</p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="color:#999;font-size:12px">如果这不是你的操作，请忽略此邮件。</p>
        </div>`,
      }),
    });

    if (!resp.ok) {
      const body = await resp.text();
      console.warn(`[MAIL] Resend 发送失败，降级到 console mock: ${body.substring(0, 150)}`);
      // fall through to mock
    } else {
      console.log(`[MAIL] 验证码已发送至 ${email}`);
      return;
    }
  } catch (err: any) {
    console.warn(`[MAIL] 发送异常，降级到 console mock: ${err.message}`);
  }

  // Fallback: print to console
  console.log(`\n[MAIL Mock] ───────────────────────────────────
  收件人: ${email}
  验证码: ${code}
  有效期: ${config.smsCodeExpiryMs / 1000} 秒
───────────────────────────────────────────\n`);
}
