import { Empty, Typography } from "antd";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Funnel,
  FunnelChart,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const { Text } = Typography;

function parseIso(value) {
  const date = value ? new Date(value) : null;
  return Number.isNaN(date?.getTime?.()) ? null : date;
}

export function buildTaskFunnel(tasks) {
  const todo = tasks.filter((task) => task.active && (task.replay || []).length <= 2 && !task.blocked).length;
  const doing = tasks.filter((task) => task.active && !task.blocked).length;
  const done = tasks.filter((task) => !task.active || task.output).length;
  return [
    { value: Math.max(todo, 0), stage: "Todo", fill: "#e8c8b4" },
    { value: Math.max(doing, 0), stage: "Doing", fill: "#d98f63" },
    { value: Math.max(done, 0), stage: "Done", fill: "#8b3f1b" },
  ];
}

export function buildAgentLoadData(agents) {
  return agents.slice(0, 10).map((agent) => ({
    name: agent.title,
    activeTasks: agent.activeTasks,
    blockedTasks: agent.blockedTasks,
  }));
}

export function buildActivityTrend(events) {
  const now = new Date();
  const buckets = [];
  for (let offset = 23; offset >= 0; offset -= 1) {
    const bucket = new Date(now);
    bucket.setMinutes(0, 0, 0);
    bucket.setHours(bucket.getHours() - offset);
    buckets.push({
      key: bucket.toISOString(),
      hour: `${bucket.getHours()}:00`,
      count: 0,
    });
  }
  events.forEach((event) => {
    const date = parseIso(event.at);
    if (!date) {
      return;
    }
    const bucketKey = new Date(date);
    bucketKey.setMinutes(0, 0, 0);
    const match = buckets.find((item) => item.key === bucketKey.toISOString());
    if (match) {
      match.count += 1;
    }
  });
  return buckets;
}

export function FunnelPanel({ data, emptyText = "暂无可用漏斗数据" }) {
  if (!data.some((item) => item.value > 0)) {
    return <Empty description={emptyText} />;
  }
  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={240}>
        <FunnelChart>
          <Tooltip />
          <Funnel dataKey="value" data={data} isAnimationActive>
            <LabelList position="right" fill="#5c453b" stroke="none" dataKey="stage" />
            {data.map((entry) => (
              <Cell key={entry.stage} fill={entry.fill} />
            ))}
          </Funnel>
        </FunnelChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AgentLoadPanel({ data, emptyText = "暂无 Agent 负载数据" }) {
  if (!data.length) {
    return <Empty description={emptyText} />;
  }
  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(110,75,55,0.14)" />
          <XAxis dataKey="name" tick={{ fill: "#6f5647", fontSize: 12 }} interval={0} angle={-20} textAnchor="end" height={54} />
          <YAxis tick={{ fill: "#6f5647", fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="activeTasks" fill="#b55a2a" radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ActivityTrendPanel({ data, emptyText = "最近 24 小时还没有活动趋势数据" }) {
  if (!data.some((item) => item.count > 0)) {
    return <Empty description={emptyText} />;
  }
  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(110,75,55,0.14)" />
          <XAxis dataKey="hour" tick={{ fill: "#6f5647", fontSize: 12 }} minTickGap={24} />
          <YAxis tick={{ fill: "#6f5647", fontSize: 12 }} allowDecimals={false} />
          <Tooltip />
          <Line type="monotone" dataKey="count" stroke="#8b3f1b" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RelayNetworkPanel({ relays, emptyText = "最近 24 小时还没有形成 handoff 网络", edgeLabel = "次", agoLabel = "前" }) {
  if (!relays.length) {
    return <Empty description={emptyText} />;
  }
  const nodeNames = [...new Set(relays.flatMap((relay) => [relay.from, relay.to]))];
  const radius = 108;
  const center = 140;
  const nodes = nodeNames.map((name, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodeNames.length, 1) - Math.PI / 2;
    return {
      name,
      x: center + Math.cos(angle) * radius,
      y: center + Math.sin(angle) * radius,
    };
  });
  const nodeMap = new Map(nodes.map((node) => [node.name, node]));
  const maxCount = Math.max(...relays.map((relay) => relay.count), 1);

  return (
    <div className="relay-network-shell">
      <svg viewBox="0 0 280 280" className="relay-network">
        {relays.map((relay) => {
          const from = nodeMap.get(relay.from);
          const to = nodeMap.get(relay.to);
          if (!from || !to) {
            return null;
          }
          return (
            <g key={`${relay.from}-${relay.to}`}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="rgba(181, 90, 42, 0.28)"
                strokeWidth={1 + (relay.count / maxCount) * 5}
                strokeLinecap="round"
              />
            </g>
          );
        })}
        {nodes.map((node) => (
          <g key={node.name}>
            <circle cx={node.x} cy={node.y} r="18" fill="#fff7f0" stroke="#b55a2a" strokeWidth="2" />
            <text x={node.x} y={node.y + 32} textAnchor="middle" fontSize="11" fill="#5c453b">
              {node.name}
            </text>
          </g>
        ))}
      </svg>
      <div className="relay-network-legend">
        {relays.slice(0, 6).map((relay) => (
          <div className="relay-legend-row" key={`${relay.from}-${relay.to}`}>
            <Text strong>{relay.from} → {relay.to}</Text>
            <Text type="secondary">{relay.count} {edgeLabel} · {relay.lastAgo || agoLabel}</Text>
          </div>
        ))}
      </div>
    </div>
  );
}
