import { Alert, Button, Card, Col, Descriptions, Empty, Form, Input, List, Row, Select, Space, Tag, Typography } from "antd";
import { MessageOutlined } from "@ant-design/icons";
import { formatListText, safeArray } from "../ui.jsx";

const { Text } = Typography;
const { TextArea } = Input;

function ConversationsView({
  permissions,
  sessions,
  selectedConversation,
  selectedConversationKey,
  transcript,
  transcriptLoading,
  dashboard,
  onOpenConversation,
  onSendConversation,
}) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={10}>
        <Card title="会话列表" extra={<Text type="secondary">{sessions.length} 个真实会话</Text>}>
          <List
            itemLayout="vertical"
            dataSource={sessions}
            locale={{ emptyText: "当前没有会话。" }}
            renderItem={(item) => (
              <List.Item
                className={item.key === selectedConversationKey ? "selectable-item active" : "selectable-item"}
                onClick={() => onOpenConversation(item)}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{item.label}</Text>
                      {item.talkable ? <Tag color="green">可对话</Tag> : <Tag>只读</Tag>}
                    </Space>
                  }
                  description={formatListText([item.agentLabel, item.sourceLabel, item.updatedAgo])}
                />
                <Text type="secondary">{item.preview || "当前没有摘要。"}</Text>
              </List.Item>
            )}
          />
        </Card>
      </Col>

      <Col xs={24} xl={14}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card title="对话现场" extra={selectedConversation ? <Tag color="processing">{selectedConversation.agentLabel}</Tag> : null}>
            {transcriptLoading ? (
              <Empty description="正在载入 transcript" />
            ) : transcript ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Descriptions size="small" column={2}>
                  <Descriptions.Item label="Agent">{selectedConversation?.agentLabel}</Descriptions.Item>
                  <Descriptions.Item label="模型">{transcript?.meta?.model || selectedConversation?.model || "unknown"}</Descriptions.Item>
                  <Descriptions.Item label="轮次">{transcript?.stats?.turns || 0}</Descriptions.Item>
                  <Descriptions.Item label="工具消息">{transcript?.stats?.toolMessages || 0}</Descriptions.Item>
                </Descriptions>
                <List
                  dataSource={safeArray(transcript.items)}
                  locale={{ emptyText: "该会话还没有 transcript。" }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={formatListText([item.title, item.at])}
                        description={<div className="transcript-bubble">{item.text || " "}</div>}
                      />
                    </List.Item>
                  )}
                />
              </Space>
            ) : (
              <Empty description="先从左侧选中一条真实会话" />
            )}
          </Card>

          <Card title="继续对话">
            {permissions.conversationWrite ? (
              <Form
                layout="vertical"
                onFinish={onSendConversation}
                initialValues={{
                  agentId: selectedConversation?.agentId || safeArray(dashboard.agents)[0]?.id,
                  continueSession: Boolean(selectedConversation?.talkable),
                  thinking: "low",
                }}
              >
                <Form.Item label="目标 Agent" name="agentId" rules={[{ required: true, message: "请选择 Agent" }]}>
                  <Select
                    options={safeArray(dashboard.agents).map((agent) => ({
                      value: agent.id,
                      label: `${agent.title} · ${agent.id}`,
                    }))}
                  />
                </Form.Item>
                <Form.Item label="Thinking" name="thinking">
                  <Select
                    options={["off", "minimal", "low", "medium", "high"].map((value) => ({
                      value,
                      label: value,
                    }))}
                  />
                </Form.Item>
                <Form.Item label="消息内容" name="message" rules={[{ required: true, message: "请输入消息" }]}>
                  <TextArea rows={5} placeholder="例如：请告诉我今天尚书省还没收口的事项和下一步建议。" />
                </Form.Item>
                <Button type="primary" icon={<MessageOutlined />} htmlType="submit">
                  发送消息
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号只有查看 transcript 的权限。" />
            )}
          </Card>
        </Space>
      </Col>
    </Row>
  );
}

export default ConversationsView;
