// ─────────────────────────────────────────────
// 阿里云短信服务
// 未配置时自动 fallback 到 console mock
// ─────────────────────────────────────────────

import Dysmsapi20170525, { SendSmsRequest } from '@alicloud/dysmsapi20170525';
import { $OpenApiUtil } from '@alicloud/openapi-core';
import { config } from '../config';

let client: Dysmsapi20170525 | null = null;

function getClient(): Dysmsapi20170525 {
  if (!client) {
    const openApiConfig = new ($OpenApiUtil as any).Config({
      accessKeyId: config.smsAccessKeyId,
      accessKeySecret: config.smsProviderKey,
      endpoint: 'dysmsapi.aliyuncs.com',
    });
    client = new Dysmsapi20170525(openApiConfig);
  }
  return client;
}

export async function sendSmsCode(phone: string, code: string): Promise<void> {
  if (!config.smsAccessKeyId || !config.smsTemplateCode) {
    console.log(`[SMS Mock] 手机号: ${phone}  验证码: ${code}`);
    return;
  }

  const req = new SendSmsRequest({
    phoneNumbers: phone,
    signName: config.smsSignName,
    templateCode: config.smsTemplateCode,
    templateParam: JSON.stringify({ code }),
  });

  const resp = await getClient().sendSms(req);
  if (resp.body?.code !== 'OK') {
    throw new Error(`阿里云短信发送失败: ${resp.body?.code} — ${resp.body?.message}`);
  }
  console.log(`[SMS] 验证码已发送至 ${phone}，RequestId: ${resp.body?.requestId}`);
}
