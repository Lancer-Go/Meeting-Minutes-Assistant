// 认证辅助（M3 TG-4）：JWT 存取、请求头注入、401 跳转、带 token 下载
(function () {
  var KEY = 'mma_token';

  window.getToken = function () {
    return localStorage.getItem(KEY) || '';
  };

  window.isLoggedIn = function () {
    return !!window.getToken();
  };

  window.setToken = function (token) {
    localStorage.setItem(KEY, token);
  };

  window.logout = function () {
    localStorage.removeItem(KEY);
    location.href = '/login.html';
  };

  // 带 Authorization 头的 fetch；401 自动登出跳转
  window.apiFetch = async function (url, opts) {
    opts = opts || {};
    var headers = Object.assign({}, opts.headers || {});
    var token = window.getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    var resp = await fetch(url, Object.assign({}, opts, { headers: headers }));
    if (resp.status === 401) { window.logout(); throw new Error('未登录或登录已过期'); }
    return resp;
  };

  // 带 token 下载文件（纪要 / 转写），规避 <a download> 不带 Authorization 的问题
  window.downloadFile = async function (url, filename) {
    try {
      var resp = await window.apiFetch(url);
      if (!resp.ok) throw new Error('下载失败：' + resp.status);
      var blob = await resp.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) { alert(e.message); }
  };
})();
