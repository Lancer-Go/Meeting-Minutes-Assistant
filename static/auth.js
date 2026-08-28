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

  // 带进度回调的文件上传（XHR）：fetch 无上传进度能力，改用 XMLHttpRequest 的
  // xhr.upload.onprogress 采集真实字节进度。行为对齐 apiFetch（Bearer 头 / 401 登出）。
  window.uploadFile = function (url, file, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url);
      var token = window.getToken();
      if (token) xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = function (e) {
          if (e.lengthComputable) onProgress(e.loaded, e.total);
        };
      }
      xhr.onload = function () {
        if (xhr.status === 401) { window.logout(); reject(new Error('未登录或登录已过期')); return; }
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e2) { /* 非 JSON 响应 */ }
        resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, data: data });
      };
      xhr.onerror = function () { reject(new Error('网络错误，上传中断')); };
      xhr.onabort = function () { reject(new Error('上传已取消')); };
      var form = new FormData();
      form.append('file', file);
      xhr.send(form);
    });
  };
})();
