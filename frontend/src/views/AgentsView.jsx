import { Card, Table, Typography } from "antd";
import { statusTag } from "../ui.jsx";

const { Text } = Typography;

function AgentsView({ agents, onSelectAgent }) {
  return (
    <Card title="Agent 运营台" extra={<Text type="secondary">参考 Ant Design 的 roster + table 工作台</Text>}>
      <Table
        rowKey="id"
        dataSource={agents}
        onRow={(record) => ({
          onClick: () => onSelectAgent(record.id),
        })}
        columns={[
          { title: "Agent", dataIndex: "title", width: 180 },
          { title: "名称", dataIndex: "name", width: 180 },
          { title: "状态", dataIndex: "status", width: 120, render: (value) => statusTag(value) },
          { title: "活跃任务", dataIndex: "activeTasks", width: 120 },
          { title: "阻塞", dataIndex: "blockedTasks", width: 100 },
          { title: "24h 接力", dataIndex: "handoffs24h", width: 120 },
          { title: "焦点", dataIndex: "focus", ellipsis: true },
          { title: "最近信号", dataIndex: "lastSeenAgo", width: 120 },
        ]}
      />
    </Card>
  );
}

export default AgentsView;
