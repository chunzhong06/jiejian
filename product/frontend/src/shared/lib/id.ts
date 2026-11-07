// 草稿项沿用调用者的完整前缀；后缀固定为 UUID 的前 16 个十六进制字符。
export const prefixedId = (prefix: string) => prefix + crypto.randomUUID().replaceAll('-', '').slice(0, 16)
