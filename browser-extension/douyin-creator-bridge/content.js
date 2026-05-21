const zh = {
  wan: '\u4e07',
  qian: '\u5343',
  play: ['\u64ad\u653e\u91cf', '\u64ad\u653e', '\u89c2\u770b\u91cf'],
  like: ['\u70b9\u8d5e\u91cf', '\u70b9\u8d5e'],
  comment: ['\u8bc4\u8bba\u91cf', '\u8bc4\u8bba'],
  favorite: ['\u6536\u85cf\u91cf', '\u6536\u85cf'],
  share: ['\u5206\u4eab\u91cf', '\u5206\u4eab'],
  completion: ['\u5b8c\u64ad\u7387'],
  avgWatch: ['\u5e73\u5747\u64ad\u653e\u65f6\u957f', '\u5e73\u5747\u89c2\u770b\u65f6\u957f'],
  bounce2s: ['2s\u8df3\u51fa\u7387', '2\u79d2\u8df3\u51fa\u7387'],
  completion5s: ['5s\u5b8c\u64ad\u7387', '5\u79d2\u5b8c\u64ad\u7387'],
  avgRatio: ['\u5e73\u5747\u64ad\u653e\u5360\u6bd4'],
  searchTitle: '\u7528\u6237\u770b\u5b8c\u4f5c\u54c1\u540e\u5e38\u641c\u7684\u8bcd',
  creatorTitleSuffix: '- \u6296\u97f3\u521b\u4f5c\u8005\u4e2d\u5fc3',
};

function normalizeText(text) {
  return (text || '').replace(/\s+/g, ' ').trim();
}

function parseChineseNumber(raw) {
  if (!raw) return 0;
  const text = String(raw).replace(/,/g, '').trim();
  const match = text.match(/([\d.]+)\s*([\u4e07\u5343kK]?)/);
  if (!match) return 0;
  let value = parseFloat(match[1]);
  if (!Number.isFinite(value)) return 0;
  const unit = match[2];
  if (unit === zh.wan) value *= 10000;
  if (unit === zh.qian) value *= 1000;
  if (unit === 'k' || unit === 'K') value *= 1000;
  return Math.round(value);
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function findMetricByLabel(text, labels) {
  for (const label of labels) {
    const pattern = new RegExp(`${escapeRegExp(label)}\\s*[:：]?\\s*([\\d.,]+\\s*[\\u4e07\\u5343kK]?)`);
    const match = text.match(pattern);
    if (match) return parseChineseNumber(match[1]);
  }
  return 0;
}

function findPercentByLabel(text, labels) {
  for (const label of labels) {
    const pattern = new RegExp(`${escapeRegExp(label)}\\s*[:：]?\\s*([\\d.]+)\\s*%`);
    const match = text.match(pattern);
    if (match) return parseFloat(match[1]) || 0;
  }
  return 0;
}

function findSecondsByLabel(text, labels) {
  for (const label of labels) {
    const pattern = new RegExp(`${escapeRegExp(label)}\\s*[:：]?\\s*([\\d.]+)\\s*(?:秒|s)`);
    const match = text.match(pattern);
    if (match) return parseFloat(match[1]) || 0;
  }
  return 0;
}

function findTitle() {
  const candidates = [
    document.querySelector('h1'),
    document.querySelector('[class*="title"]'),
    document.querySelector('[class*="Title"]'),
  ];
  for (const el of candidates) {
    const text = normalizeText(el?.innerText || el?.textContent);
    if (text && text.length > 1 && text.length < 120) return text;
  }
  const metaTitle = normalizeText(document.title || '');
  return metaTitle.replace(zh.creatorTitleSuffix, '').slice(0, 120);
}

function parsePublishDateTime(rawText) {
  const text = normalizeText(rawText);
  const patterns = [
    /(?:发布时间|发布日期|发布于|发布)\s*[:：]?\s*(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*(\d{1,2}:\d{2})?/,
    /(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*(\d{1,2}:\d{2})?/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const year = match[1];
    const month = String(parseInt(match[2], 10)).padStart(2, '0');
    const day = String(parseInt(match[3], 10)).padStart(2, '0');
    const time = match[4] || '';
    return {
      publish_date: `${year}-${month}-${day}`,
      publish_time: time,
    };
  }
  return { publish_date: '', publish_time: '' };
}

function parsePostWatchSearchTerms(rawText) {
  const idx = rawText.indexOf(zh.searchTitle);
  if (idx < 0) return [];
  const segment = rawText.slice(idx + zh.searchTitle.length, idx + zh.searchTitle.length + 800);
  const stopWords = ['总览', '流量分析', '观众分析', '评论热词', '观看趋势'];
  let clean = segment;
  for (const stop of stopWords) {
    const stopIdx = clean.indexOf(stop);
    if (stopIdx > 20) clean = clean.slice(0, stopIdx);
  }
  const terms = [];
  const regex = /(?:^|\s)(\d{1,2})\s+(.+?)(?:\s+([\d.]+)\s*%)?(?=\s+\d{1,2}\s+|$)/g;
  let match;
  while ((match = regex.exec(clean)) && terms.length < 10) {
    const keyword = normalizeText(match[2]).replace(/\d+$/, '').trim();
    if (!keyword || keyword.length > 80) continue;
    terms.push({
      rank: parseInt(match[1], 10),
      keyword,
      ratio: match[3] ? parseFloat(match[3]) : 0,
    });
  }
  return terms;
}

function parseDropPoints(rawText) {
  const points = [];
  const regex = /(\d{1,2}):(\d{2})\s*(低谷\d*)/g;
  let match;
  while ((match = regex.exec(rawText)) && points.length < 10) {
    points.push({
      second: parseInt(match[1], 10) * 60 + parseInt(match[2], 10),
      label: match[3],
    });
  }
  return points;
}

function captureVisibleData() {
  const pageText = normalizeText(document.body?.innerText || '');
  const url = location.href;
  const title = findTitle();
  const publish = parsePublishDateTime(pageText);
  const itemMatch = url.match(/work-detail\/(\d+)/);
  const itemId = itemMatch ? itemMatch[1] : '';
  return {
    source: 'douyin_creator_extension',
    page_url: url,
    item_id: itemId,
    title,
    publish_date: publish.publish_date,
    publish_time: publish.publish_time,
    play_count: findMetricByLabel(pageText, zh.play),
    like_count: findMetricByLabel(pageText, zh.like),
    comment_count: findMetricByLabel(pageText, zh.comment),
    favorite_count: findMetricByLabel(pageText, zh.favorite),
    share_count: findMetricByLabel(pageText, zh.share),
    completion_rate: findPercentByLabel(pageText, zh.completion),
    avg_watch_seconds: findSecondsByLabel(pageText, zh.avgWatch),
    bounce_2s_rate: findPercentByLabel(pageText, zh.bounce2s),
    completion_5s_rate: findPercentByLabel(pageText, zh.completion5s),
    avg_watch_ratio: findPercentByLabel(pageText, zh.avgRatio),
    post_watch_search_terms: parsePostWatchSearchTerms(pageText),
    watch_trend: pageText.includes('\u89c2\u770b\u8d8b\u52bf') ? '\u5df2\u8bc6\u522b\u5230\u89c2\u770b\u8d8b\u52bf\u56fe\uff0c\u53ef\u89c1\u6570\u636e\u5df2\u5165\u5e93\u3002' : '',
    drop_points: parseDropPoints(pageText),
    raw_text: pageText.slice(0, 12000),
    captured_at: new Date().toISOString(),
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'DATALENS_CAPTURE_WORK') return;
  try {
    const payload = captureVisibleData();
    if (!payload.title && !payload.item_id) {
      sendResponse({ ok: false, error: '\u6ca1\u6709\u8bc6\u522b\u5230\u4f5c\u54c1\u6807\u9898\u6216\u4f5c\u54c1ID\u3002' });
      return;
    }
    sendResponse({ ok: true, payload });
  } catch (err) {
    sendResponse({ ok: false, error: err.message || String(err) });
  }
});
