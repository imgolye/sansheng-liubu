import { Tag } from "antd";

export const STATUS_COLOR = {
  active: "processing",
  waiting: "warning",
  blocked: "error",
  standby: "default",
  idle: "default",
  done: "success",
  ready: "success",
  warning: "warning",
  error: "error",
};

export function formatListText(parts) {
  return parts.filter(Boolean).join(" · ");
}

export function metricCards(metrics = {}) {
  return [
    { title: "活跃任务", value: metrics.activeTasks || 0, suffix: "条" },
    { title: "活跃 Agent", value: metrics.activeAgents || 0, suffix: "个" },
    { title: "阻塞任务", value: metrics.blockedTasks || 0, suffix: "条" },
    { title: "今日完成", value: metrics.completedToday || 0, suffix: "条" },
    { title: "24h 接力", value: metrics.handoffs24h || 0, suffix: "次" },
    { title: "1h 信号", value: metrics.signals1h || 0, suffix: "条" },
  ];
}

export function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

export function statusTag(value) {
  return <Tag color={STATUS_COLOR[String(value).toLowerCase()] || "default"}>{value || "unknown"}</Tag>;
}
