/**
 * 小红书 x-s 签名算法 JS 补环境文件（占位）
 *
 * 使用方式：
 *   将真实的签名 JS 代码替换此文件，保证导出一个名为 sign 的函数：
 *
 *   function sign(uri, data, cookie) {
 *     // 返回 { "x-s": "...", "x-t": "...", "x-s-common": "..." }
 *   }
 *
 * 推荐来源：
 *   - xhshow 项目提供的 JS 补环境文件
 *   - 自行通过 Chrome DevTools 抓包逆向提取
 *
 * 注意：此占位文件不会产生有效签名，仅用于开发调试。
 */

function sign(uri, data, cookie) {
  var ts = String(Date.now());
  return {
    "x-s": "placeholder_" + ts,
    "x-t": ts,
    "x-s-common": ""
  };
}
