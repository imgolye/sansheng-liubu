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
  t,
}) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={10}>
        <Card title={t("conversations.listTitle")} extra={<Text type="secondary">{sessions.length} {t("conversations.realSessions")}</Text>} className="workspace-card">
          <List
            itemLayout="vertical"
            dataSource={sessions}
            locale={{ emptyText: t("conversations.emptySessions") }}
            renderItem={(item) => (
              <List.Item
                className={item.key === selectedConversationKey ? "selectable-item active" : "selectable-item"}
                onClick={() => onOpenConversation(item)}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{item.label}</Text>
                      {item.talkable ? <Tag color="green">{t("conversations.talkable")}</Tag> : <Tag>{t("conversations.readonly")}</Tag>}
                    </Space>
                  }
                  description={formatListText([item.agentLabel, item.sourceLabel, item.updatedAgo])}
                />
                <Text type="secondary">{item.preview || t("conversations.noPreview")}</Text>
              </List.Item>
            )}
          />
        </Card>
      </Col>

      <Col xs={24} xl={14}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Card title={t("conversations.sceneTitle")} extra={selectedConversation ? <Tag color="processing">{selectedConversation.agentLabel}</Tag> : null} className="workspace-card">
            {transcriptLoading ? (
              <Empty description={t("conversations.loadingTranscript")} />
            ) : transcript ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Descriptions size="small" column={2}>
                  <Descriptions.Item label="Agent">{selectedConversation?.agentLabel}</Descriptions.Item>
                  <Descriptions.Item label={t("conversations.model")}>{transcript?.meta?.model || selectedConversation?.model || "unknown"}</Descriptions.Item>
                  <Descriptions.Item label={t("conversations.turns")}>{transcript?.stats?.turns || 0}</Descriptions.Item>
                  <Descriptions.Item label={t("conversations.toolMessages")}>{transcript?.stats?.toolMessages || 0}</Descriptions.Item>
                </Descriptions>
                <List
                  dataSource={safeArray(transcript.items)}
                  locale={{ emptyText: t("conversations.emptyTranscript") }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={formatListText([item.title, item.at])}
                        description={<div className="transcript-bubble">{item.text || t("conversations.noText")}</div>}
                      />
                    </List.Item>
                  )}
                />
              </Space>
            ) : (
              <Empty description={t("conversations.emptyTranscriptSelection")} />
            )}
          </Card>

          <Card title={t("conversations.continueTitle")} className="workspace-card">
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
                <Form.Item label={t("conversations.targetAgent")} name="agentId" rules={[{ required: true, message: t("conversations.chooseAgent") }]}>
                  <Select
                    options={safeArray(dashboard.agents).map((agent) => ({
                      value: agent.id,
                      label: `${agent.title} · ${agent.id}`,
                    }))}
                  />
                </Form.Item>
                <Form.Item label={t("conversations.thinking")} name="thinking">
                  <Select
                    options={["off", "minimal", "low", "medium", "high"].map((value) => ({
                      value,
                      label: value,
                    }))}
                  />
                </Form.Item>
                <Form.Item label={t("conversations.message")} name="message" rules={[{ required: true, message: t("conversations.enterMessage") }]}>
                  <TextArea rows={5} placeholder={t("conversations.messagePlaceholder")} />
                </Form.Item>
                <Button type="primary" icon={<MessageOutlined />} htmlType="submit">
                  {t("conversations.send")}
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message={t("conversations.transcriptOnly")} />
            )}
          </Card>
        </Space>
      </Col>
    </Row>
  );
}

export default ConversationsView;
