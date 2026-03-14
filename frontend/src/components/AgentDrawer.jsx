import { Card, Descriptions, Drawer, List, Space, Typography } from "antd";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Paragraph } = Typography;

function AgentDrawer({ agent, open, onClose }) {
  return (
    <Drawer
      title={agent ? `${agent.title} · Agent 详情` : ""}
      open={open}
      width={720}
      onClose={onClose}
    >
      {agent ? (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="状态">{statusTag(agent.status)}</Descriptions.Item>
            <Descriptions.Item label="模型">{agent.model}</Descriptions.Item>
            <Descriptions.Item label="活跃任务">{agent.activeTasks}</Descriptions.Item>
            <Descriptions.Item label="阻塞">{agent.blockedTasks}</Descriptions.Item>
            <Descriptions.Item label="24h 接力">{agent.handoffs24h}</Descriptions.Item>
            <Descriptions.Item label="最近信号">{agent.lastSeenAgo}</Descriptions.Item>
          </Descriptions>
          <Card size="small" title="当前焦点">
            <Paragraph>{agent.focus || "当前没有明确 progress signal。"}</Paragraph>
          </Card>
          <Card size="small" title="在手任务">
            <List
              dataSource={safeArray(agent.activeTaskCards)}
              locale={{ emptyText: "当前没有正在承担的活跃任务。" }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta title={item.title} description={formatListText([item.meta, item.detail])} />
                </List.Item>
              )}
            />
          </Card>
          <Card size="small" title="最近信号">
            <List
              dataSource={safeArray(agent.recentSignals)}
              locale={{ emptyText: "最近没有新的协同信号。" }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta title={item.title} description={formatListText([item.meta, item.detail])} />
                </List.Item>
              )}
            />
          </Card>
        </Space>
      ) : null}
    </Drawer>
  );
}

export default AgentDrawer;
