const STORAGE_KEY = 'aiknowledge_console_config_v1';

const defaultScenario = {
  tenantId: 'tenant-demo',
  teamId: 'risk-platform',
  userId: 'ops-owner',
  clientType: 'console',
  repoId: 'demo-repo',
  branchName: 'feature/order-risk-hardening',
  taskId: 'RISK-2048',
  path: 'src/order/risk/check.ts',
  profileInstruction: '订单风控路径下的实现必须补充回归检查清单，并在涉及黑名单校验时记录命中原因。',
  eventOne:
    '订单风控规则必须通过统一规则引擎接入，并补充路径级回归检查项，避免在订单入口散落特判逻辑。',
  eventTwo:
    '修复后回归通过，形成可复用案例，并补充渠道黑名单命中原因记录，便于值班排查和复盘。',
  query: '为订单风控增加渠道黑名单校验与回归检查',
};

const state = {
  sessionId: '',
  signalIds: [],
  knowledgeId: '',
  retrievalRequestId: '',
  profileId: '',
  workflow: {
    profile: false,
    session: false,
    events: false,
    extract: false,
    approve: false,
    retrieve: false,
  },
};

const elements = {
  baseUrlInput: document.querySelector('#baseUrlInput'),
  apiKeyInput: document.querySelector('#apiKeyInput'),
  tenantInput: document.querySelector('#tenantInput'),
  teamInput: document.querySelector('#teamInput'),
  userInput: document.querySelector('#userInput'),
  clientTypeInput: document.querySelector('#clientTypeInput'),
  repoIdInput: document.querySelector('#repoIdInput'),
  branchInput: document.querySelector('#branchInput'),
  taskIdInput: document.querySelector('#taskIdInput'),
  pathInput: document.querySelector('#pathInput'),
  profileInstructionInput: document.querySelector('#profileInstructionInput'),
  eventOneInput: document.querySelector('#eventOneInput'),
  eventTwoInput: document.querySelector('#eventTwoInput'),
  queryInput: document.querySelector('#queryInput'),
  healthStatus: document.querySelector('#healthStatus'),
  llmStatus: document.querySelector('#llmStatus'),
  vectorStatus: document.querySelector('#vectorStatus'),
  versionStatus: document.querySelector('#versionStatus'),
  sessionChip: document.querySelector('#sessionChip'),
  knowledgeChip: document.querySelector('#knowledgeChip'),
  requestChip: document.querySelector('#requestChip'),
  healthButton: document.querySelector('#healthButton'),
  verifyLlmButton: document.querySelector('#verifyLlmButton'),
  saveConfigButton: document.querySelector('#saveConfigButton'),
  presetButton: document.querySelector('#presetButton'),
  runDemoButton: document.querySelector('#runDemoButton'),
  profileButton: document.querySelector('#profileButton'),
  sessionButton: document.querySelector('#sessionButton'),
  eventsButton: document.querySelector('#eventsButton'),
  extractButton: document.querySelector('#extractButton'),
  approveButton: document.querySelector('#approveButton'),
  retrieveButton: document.querySelector('#retrieveButton'),
  feedbackButton: document.querySelector('#feedbackButton'),
  auditButton: document.querySelector('#auditButton'),
  workflowBadge: document.querySelector('#workflowBadge'),
  knowledgeStatusTag: document.querySelector('#knowledgeStatusTag'),
  retrievalStatusTag: document.querySelector('#retrievalStatusTag'),
  responseTag: document.querySelector('#responseTag'),
  knowledgeSummary: document.querySelector('#knowledgeSummary'),
  retrievalSummary: document.querySelector('#retrievalSummary'),
  auditSummary: document.querySelector('#auditSummary'),
  knowledgeJson: document.querySelector('#knowledgeJson'),
  retrievalJson: document.querySelector('#retrievalJson'),
  auditJson: document.querySelector('#auditJson'),
  responseJson: document.querySelector('#responseJson'),
  activityLog: document.querySelector('#activityLog'),
};

function makeId(prefix) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeBaseUrl(value) {
  return (value || window.location.origin).trim().replace(/\/+$/, '');
}

function getConfig() {
  return {
    baseUrl: normalizeBaseUrl(elements.baseUrlInput.value),
    apiKey: elements.apiKeyInput.value.trim(),
    tenantId: elements.tenantInput.value.trim(),
    teamId: elements.teamInput.value.trim(),
    userId: elements.userInput.value.trim(),
    clientType: elements.clientTypeInput.value.trim() || 'console',
  };
}

function getScenario() {
  return {
    repoId: elements.repoIdInput.value.trim(),
    branchName: elements.branchInput.value.trim(),
    taskId: elements.taskIdInput.value.trim(),
    path: elements.pathInput.value.trim(),
    profileInstruction: elements.profileInstructionInput.value.trim(),
    eventOne: elements.eventOneInput.value.trim(),
    eventTwo: elements.eventTwoInput.value.trim(),
    query: elements.queryInput.value.trim(),
  };
}

function saveLocalConfig() {
  const { apiKey: _apiKey, ...safeConfig } = getConfig();
  const payload = { ...safeConfig, ...getScenario() };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  appendLog('success', '本地配置已保存，敏感密钥不会写入浏览器本地存储。');
}

function applyPreset(preset) {
  elements.tenantInput.value = preset.tenantId || defaultScenario.tenantId;
  elements.teamInput.value = preset.teamId || defaultScenario.teamId;
  elements.userInput.value = preset.userId || defaultScenario.userId;
  elements.clientTypeInput.value = preset.clientType || defaultScenario.clientType;
  elements.repoIdInput.value = preset.repoId || defaultScenario.repoId;
  elements.branchInput.value = preset.branchName || defaultScenario.branchName;
  elements.taskIdInput.value = preset.taskId || defaultScenario.taskId;
  elements.pathInput.value = preset.path || defaultScenario.path;
  elements.profileInstructionInput.value = preset.profileInstruction || defaultScenario.profileInstruction;
  elements.eventOneInput.value = preset.eventOne || defaultScenario.eventOne;
  elements.eventTwoInput.value = preset.eventTwo || defaultScenario.eventTwo;
  elements.queryInput.value = preset.query || defaultScenario.query;
}

function loadLocalConfig() {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    applyPreset(defaultScenario);
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    applyPreset({ ...defaultScenario, ...parsed });
    if (parsed.baseUrl) {
      elements.baseUrlInput.value = parsed.baseUrl;
    }
  } catch (error) {
    applyPreset(defaultScenario);
    appendLog('error', `本地配置读取失败，已回退默认场景。${error.message}`);
  }
}

function appendLog(kind, message) {
  const item = document.createElement('li');
  item.className = `activity-item activity-item-${kind}`;
  item.textContent = `${new Date().toLocaleTimeString('zh-CN', { hour12: false })}  ${message}`;
  elements.activityLog.prepend(item);
}

function renderJson(target, payload) {
  target.textContent = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
}

function renderChips() {
  elements.sessionChip.textContent = state.sessionId || '未创建';
  elements.knowledgeChip.textContent = state.knowledgeId || '未生成';
  elements.requestChip.textContent = state.retrievalRequestId || '未检索';
}

function setResponseTag(label) {
  elements.responseTag.textContent = label;
}

function setBusy(button, busy, busyLabel) {
  if (!button) {
    return;
  }
  if (!button.dataset.originalLabel) {
    button.dataset.originalLabel = button.textContent;
  }
  button.disabled = busy;
  button.textContent = busy ? busyLabel : button.dataset.originalLabel;
}

function resetWorkflow() {
  Object.keys(state.workflow).forEach((key) => {
    state.workflow[key] = false;
  });
  updateWorkflowView();
}

function updateWorkflowView(activeKey = '') {
  const mapping = {
    profile: elements.profileButton,
    session: elements.sessionButton,
    events: elements.eventsButton,
    extract: elements.extractButton,
    approve: elements.approveButton,
    retrieve: elements.retrieveButton,
  };
  Object.entries(mapping).forEach(([name, button]) => {
    button.classList.toggle('is-complete', state.workflow[name]);
    button.classList.toggle('is-active', name === activeKey && !state.workflow[name]);
  });
  const completedCount = Object.values(state.workflow).filter(Boolean).length;
  elements.workflowBadge.textContent = completedCount === 6 ? '流程已完成' : `已完成 ${completedCount}/6`;
}

function markWorkflowComplete(key) {
  state.workflow[key] = true;
  updateWorkflowView();
}

async function request(method, path, payload) {
  const config = getConfig();
  const headers = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'X-Request-Id': makeId('req_ui'),
    'X-Client-Type': config.clientType,
  };
  if (config.apiKey) {
    headers.Authorization = `Bearer ${config.apiKey}`;
  }
  if (config.tenantId) {
    headers['X-Tenant-Id'] = config.tenantId;
  }
  if (config.teamId) {
    headers['X-Team-Id'] = config.teamId;
  }
  if (config.userId) {
    headers['X-User-Id'] = config.userId;
  }

  const response = await fetch(`${config.baseUrl}${path}`, {
    method,
    headers,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  renderJson(elements.responseJson, data);
  setResponseTag(`${method} ${path}`);
  if (!response.ok) {
    throw new Error(data.detail || data.message || text || `HTTP ${response.status}`);
  }
  return data;
}

function updateHealthView(payload) {
  elements.healthStatus.textContent = payload.status || 'unknown';
  elements.llmStatus.textContent = payload.llm?.configured ? payload.llm.model || 'configured' : '未配置';
  elements.vectorStatus.textContent = payload.vector_backend || 'unknown';
  elements.versionStatus.textContent = payload.version || 'unknown';
}

function buildProfilePayload() {
  const scenario = getScenario();
  return {
    scope_type: 'path',
    scope_id: scenario.path.replace(/\/[^/]+$/, ''),
    profile_type: 'coding_rule',
    content: { instructions: [scenario.profileInstruction] },
    version: 1,
    status: 'active',
  };
}

async function loadHealth() {
  const payload = await request('GET', '/healthz');
  updateHealthView(payload);
  appendLog('success', `健康检查完成，状态为 ${payload.status}。`);
  return payload;
}

async function verifyLlm() {
  const payload = await request('POST', '/api/v1/llm/verify', {
    prompt: 'Reply with ok only.',
    max_tokens: 32,
  });
  appendLog('success', `LLM 连通验证完成，响应为 ${payload.data?.response_text || '空'}。`);
  return payload;
}

async function ensureProfile() {
  updateWorkflowView('profile');
  const payload = buildProfilePayload();
  state.profileId = state.profileId || makeId('cfg_console');
  const response = await request('PUT', `/api/v1/config/profile/${state.profileId}`, payload);
  markWorkflowComplete('profile');
  appendLog('success', `路径规则已写入 ${payload.scope_id}。`);
  return response;
}

async function createSession() {
  updateWorkflowView('session');
  const scenario = getScenario();
  const response = await request('POST', '/api/v1/sessions', {
    repo_id: scenario.repoId,
    branch_name: scenario.branchName,
    task_id: scenario.taskId,
    client_type: getConfig().clientType,
  });
  state.sessionId = response.data.session_id;
  renderChips();
  markWorkflowComplete('session');
  appendLog('success', `会话已创建：${state.sessionId}。`);
  return response;
}

async function appendEvents() {
  if (!state.sessionId) {
    throw new Error('请先创建会话。');
  }
  updateWorkflowView('events');
  const scenario = getScenario();
  const response = await request('POST', '/api/v1/context/events', {
    session_id: state.sessionId,
    events: [
      {
        event_type: 'prompt',
        summary: scenario.eventOne,
        file_paths: [scenario.path],
        symbol_names: ['validateOrderRisk'],
      },
      {
        event_type: 'test_result',
        summary: scenario.eventTwo,
        file_paths: [scenario.path],
        symbol_names: ['validateOrderRisk'],
      },
    ],
  });
  state.signalIds = response.data.created_signal_ids || [];
  markWorkflowComplete('events');
  appendLog('success', `事件上报完成，生成 ${state.signalIds.length} 个信号。`);
  return response;
}

function summarizeKnowledge(payload) {
  const content = payload.data.content || {};
  elements.knowledgeSummary.textContent = [
    `标题：${payload.data.title}`,
    `类型：${payload.data.knowledge_type} / ${payload.data.memory_type}`,
    `作用域：${payload.data.scope_type}:${payload.data.scope_id}`,
    `状态：${payload.data.status}`,
    `摘要：${content.summary || content.background || content.conclusion || '无'}`,
  ].join('\n');
  elements.knowledgeStatusTag.textContent = payload.data.status || 'draft';
  renderJson(elements.knowledgeJson, payload);
}

async function extractKnowledge() {
  if (!state.signalIds.length) {
    throw new Error('请先上报事件。');
  }
  updateWorkflowView('extract');
  const response = await request('POST', '/api/v1/knowledge/extract', {
    signal_ids: state.signalIds,
    force: false,
  });
  const firstItem = response.data.items?.[0];
  if (!firstItem) {
    throw new Error('抽取未返回知识条目。');
  }
  state.knowledgeId = firstItem.knowledge_id;
  renderChips();
  const knowledgeDetail = await request('GET', `/api/v1/knowledge/${state.knowledgeId}`);
  summarizeKnowledge(knowledgeDetail);
  markWorkflowComplete('extract');
  appendLog('success', `知识抽取完成：${knowledgeDetail.data.title}。`);
  return response;
}

async function approveKnowledge() {
  if (!state.knowledgeId) {
    throw new Error('请先完成知识抽取。');
  }
  updateWorkflowView('approve');
  const response = await request('POST', '/api/v1/knowledge/review', {
    knowledge_id: state.knowledgeId,
    decision: 'approve',
    reviewer_id: 'console-reviewer',
    comment: 'Console auto approval',
  });
  const knowledgeDetail = await request('GET', `/api/v1/knowledge/${state.knowledgeId}`);
  summarizeKnowledge(knowledgeDetail);
  markWorkflowComplete('approve');
  appendLog('success', `知识已审核通过，状态为 ${response.data.status}。`);
  return response;
}

function summarizeRetrieval(payload) {
  const sources = payload.data.sources || [];
  elements.retrievalSummary.textContent = [
    `Context Summary：${payload.data.context_summary || '无'}`,
    `规则数：${(payload.data.rules || []).length}`,
    `案例数：${(payload.data.cases || []).length}`,
    `流程数：${(payload.data.procedures || []).length}`,
    `来源：${sources.map((item) => item.knowledge_id).join(', ') || '无'}`,
  ].join('\n');
  elements.retrievalStatusTag.textContent = '已检索';
  renderJson(elements.retrievalJson, payload);
}

async function retrieveContext() {
  if (!state.sessionId) {
    throw new Error('请先创建会话。');
  }
  updateWorkflowView('retrieve');
  const scenario = getScenario();
  const response = await request('POST', '/api/v1/retrieval/query', {
    session_id: state.sessionId,
    query: scenario.query,
    query_type: 'feature_impl',
    repo_id: scenario.repoId,
    branch_name: scenario.branchName,
    file_paths: [scenario.path],
    token_budget: 2200,
  });
  state.retrievalRequestId = response.request_id;
  renderChips();
  summarizeRetrieval(response);
  markWorkflowComplete('retrieve');
  appendLog('success', `上下文检索完成，请求号 ${state.retrievalRequestId}。`);
  return response;
}

async function loadAuditLogs() {
  const payload = await request('GET', '/api/v1/audit/logs?limit=12');
  const items = payload.data || [];
  elements.auditSummary.textContent =
    items.length > 0
      ? items
          .slice(0, 5)
          .map((item) => `${item.action} · ${item.resource_type} · ${item.resource_id}`)
          .join('\n')
      : '暂无审计数据';
  renderJson(elements.auditJson, payload);
  appendLog('success', `审计日志已刷新，共返回 ${items.length} 条。`);
  return payload;
}

async function submitFeedbackAndAudit() {
  if (!state.knowledgeId || !state.retrievalRequestId) {
    throw new Error('请先完成知识抽取与检索。');
  }
  await request('POST', '/api/v1/feedback/knowledge', {
    knowledge_id: state.knowledgeId,
    request_id: state.retrievalRequestId,
    feedback_type: 'accepted',
    feedback_score: 5,
    feedback_text: 'Console demo accepted',
    created_by: getConfig().userId || 'console-user',
  });
  await request('POST', '/api/v1/feedback/context-pack', {
    request_id: state.retrievalRequestId,
    feedback_score: 5,
    relevance_score: 5,
    completeness_score: 4,
    feedback_text: 'Console demo helpful',
    created_by: getConfig().userId || 'console-user',
  });
  appendLog('success', '反馈已提交。');
  return loadAuditLogs();
}

async function runDemo() {
  resetWorkflow();
  applyPreset(defaultScenario);
  state.profileId = '';
  state.sessionId = '';
  state.signalIds = [];
  state.knowledgeId = '';
  state.retrievalRequestId = '';
  renderChips();
  elements.knowledgeSummary.textContent = '运行抽取后，这里会显示标题、类型、作用域和摘要。';
  elements.retrievalSummary.textContent = '执行检索后，这里会显示 context summary、规则命中和知识命中。';
  elements.auditSummary.textContent = '完成操作后，这里会显示最近的审计动作。';
  renderJson(elements.knowledgeJson, '暂无数据');
  renderJson(elements.retrievalJson, '暂无数据');
  renderJson(elements.auditJson, '暂无数据');
  await loadHealth();
  await verifyLlm();
  await ensureProfile();
  await createSession();
  await appendEvents();
  await extractKnowledge();
  await approveKnowledge();
  await retrieveContext();
  await submitFeedbackAndAudit();
  appendLog('success', '一键真实示例已完整跑通。');
}

function attachRevealAnimation() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.16 },
  );
  document.querySelectorAll('[data-reveal]').forEach((node) => observer.observe(node));
}

async function withTask(button, label, fn) {
  setBusy(button, true, label);
  try {
    return await fn();
  } catch (error) {
    appendLog('error', error.message);
    return null;
  } finally {
    setBusy(button, false, label);
  }
}

function wireEvents() {
  elements.saveConfigButton.addEventListener('click', saveLocalConfig);
  elements.presetButton.addEventListener('click', () => {
    applyPreset(defaultScenario);
    appendLog('success', '默认场景已恢复。');
  });
  elements.healthButton.addEventListener('click', () => withTask(elements.healthButton, '检测中...', loadHealth));
  elements.verifyLlmButton.addEventListener('click', () =>
    withTask(elements.verifyLlmButton, '验证中...', verifyLlm),
  );
  elements.profileButton.addEventListener('click', () =>
    withTask(elements.profileButton, '处理中...', ensureProfile),
  );
  elements.sessionButton.addEventListener('click', () =>
    withTask(elements.sessionButton, '处理中...', createSession),
  );
  elements.eventsButton.addEventListener('click', () =>
    withTask(elements.eventsButton, '处理中...', appendEvents),
  );
  elements.extractButton.addEventListener('click', () =>
    withTask(elements.extractButton, '处理中...', extractKnowledge),
  );
  elements.approveButton.addEventListener('click', () =>
    withTask(elements.approveButton, '处理中...', approveKnowledge),
  );
  elements.retrieveButton.addEventListener('click', () =>
    withTask(elements.retrieveButton, '处理中...', retrieveContext),
  );
  elements.feedbackButton.addEventListener('click', () =>
    withTask(elements.feedbackButton, '处理中...', submitFeedbackAndAudit),
  );
  elements.auditButton.addEventListener('click', () =>
    withTask(elements.auditButton, '处理中...', loadAuditLogs),
  );
  elements.runDemoButton.addEventListener('click', () =>
    withTask(elements.runDemoButton, '执行中...', runDemo),
  );
}

async function bootstrap() {
  loadLocalConfig();
  attachRevealAnimation();
  wireEvents();
  renderChips();
  resetWorkflow();
  try {
    await loadHealth();
  } catch (error) {
    appendLog('error', `初始化健康检查失败：${error.message}`);
  }
}

bootstrap();
