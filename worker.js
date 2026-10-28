// Cloudflare Worker：以正确的 Content-Type 分发 OTA 屏蔽描述文件。
//
// 存在的意义：GitHub raw 对纯文本的 .mobileconfig 返回 text/plain，
// Safari 可能把 XML 渲染成页面而不是提示安装。这里强制
// content-type: application/octet-stream + content-disposition: attachment，
// 保证设备一定走下载路径。
//
// 文件内容不在这里硬编码，而是由 wrangler 在打包时从
// block-ota.mobileconfig 导入（见 wrangler.toml 的 rules 段），
// 保证仓库里只有一份真相，不会出现 Worker 与产物不一致。

import profile from "./block-ota.mobileconfig";

const FILENAME = "block-ota.mobileconfig";

// 运行时计算实际下发字节的 SHA-256，供核对。
// 注意：这个哈希和文件同源，只能证明"下发的东西没被中途改动"，
// 不能替代在本地对仓库源码的审计。
async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const PROFILE_HEADERS = (hash) => ({
  "content-type": "application/octet-stream",
  "content-disposition": `attachment; filename="${FILENAME}"`,
  "content-length": String(new TextEncoder().encode(profile).length),
  etag: `"${hash}"`,
  "cache-control": "public, max-age=300",
  "x-content-type-options": "nosniff",
});

export default {
  async fetch(request) {
    const { pathname } = new URL(request.url);

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed\n", {
        status: 405,
        headers: { allow: "GET, HEAD", "content-type": "text/plain; charset=utf-8" },
      });
    }

    const hash = await sha256(profile);

    if (pathname === `/${FILENAME}`) {
      if (request.headers.get("if-none-match") === `"${hash}"`) {
        return new Response(null, { status: 304, headers: { etag: `"${hash}"` } });
      }
      return new Response(request.method === "HEAD" ? null : profile, {
        status: 200,
        headers: PROFILE_HEADERS(hash),
      });
    }

    if (pathname === "/sha256") {
      return new Response(`${hash}  ${FILENAME}\n`, {
        headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
      });
    }

    if (pathname === "/" || pathname === "/index.html") {
      const body = [
        "OTA Update Blocker",
        "",
        `描述文件：/${FILENAME}`,
        "校验值：  /sha256",
        "",
        "安装：用设备 Safari 打开上面的描述文件地址，",
        "      然后到 设置 → 已下载的描述文件 → 安装 → 重启。",
        "",
        "原理与审计说明见仓库：",
        "https://github.com/ChenMeng0518/ota-block",
        "",
      ].join("\n");
      return new Response(body, {
        headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "public, max-age=3600" },
      });
    }

    return new Response("Not Found\n", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  },
};
