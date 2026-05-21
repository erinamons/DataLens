const btn = document.getElementById('sendBtn');
const statusEl = document.getElementById('status');

function setStatus(text) {
  statusEl.textContent = text;
}

btn.addEventListener('click', async () => {
  btn.disabled = true;
  setStatus('正在读取当前页面...');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id || !tab.url || !tab.url.includes('creator.douyin.com')) {
      setStatus('请先打开抖音创作者中心作品详情页。');
      return;
    }
    const response = await chrome.tabs.sendMessage(tab.id, { type: 'DATALENS_CAPTURE_WORK' });
    if (!response || !response.ok) {
      setStatus(response?.error || '页面数据读取失败。');
      return;
    }
    setStatus('正在发送到本机 DataLens...');
    const res = await fetch('http://127.0.0.1:8900/api/creator/douyin/import-current', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(response.payload),
    });
    const data = await res.json();
    if (data.success) {
      setStatus(`已写入 DataLens\n视频ID：${data.video_id}\n模式：${data.mode}`);
    } else {
      setStatus(data.error || 'DataLens 写入失败。');
    }
  } catch (err) {
    setStatus(`发送失败：${err.message || err}`);
  } finally {
    btn.disabled = false;
  }
});
