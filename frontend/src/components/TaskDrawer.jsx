import { Alert, Button, Card, Descriptions, Drawer, Form, Input, Space, Tabs, Timeline, Typography } from "antd";
import { CheckCircleOutlined, ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

function TaskDrawer({ task, open, onClose, permissions, onAction }) {
  return (
    <Drawer
      title={task ? `${task.id} · 任务工作台` : ""}
      open={open}
      width={760}
      onClose={onClose}
    >
      {task ? (
        <Tabs
          items={[
            {
              key: "overview",
              label: "概览",
              children: (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <Descriptions column={2} size="small">
                    <Descriptions.Item label="状态">{statusTag(task.state)}</Descriptions.Item>
                    <Descriptions.Item label="负责人">{task.currentAgentLabel || task.org}</Descriptions.Item>
                    <Descriptions.Item label="签收">{task.owner || "未知"}</Descriptions.Item>
                    <Descriptions.Item label="更新时间">{task.updatedAgo}</Descriptions.Item>
                  </Descriptions>
                  <Card size="small" title="当前进展">
                    <Paragraph>{task.currentUpdate || "当前没有进展摘要。"}</Paragraph>
                  </Card>
                  <Card size="small" title="任务回放">
                    <Timeline
                      items={safeArray(task.replay).map((item) => ({
                        color: item.kind === "handoff" ? "orange" : "green",
                        children: (
                          <div>
                            <Text strong>{item.headline}</Text>
                            <br />
                            <Text type="secondary">{formatListText([item.detail, item.atAgo])}</Text>
                          </div>
                        ),
                      }))}
                    />
                  </Card>
                </Space>
              ),
            },
            {
              key: "progress",
              label: "推进",
              children: permissions.taskWrite ? (
                <Form
                  layout="vertical"
                  onFinish={(values) =>
                    onAction("/api/actions/task/progress", {
                      taskId: task.id,
                      message: values.message,
                      todos: values.todos || "",
                      markDoing: values.markDoing !== false,
                    })
                  }
                >
                  <Form.Item label="最新进展" name="message" rules={[{ required: true, message: "请输入进展" }]}>
                    <TextArea rows={5} placeholder="例如：正在拆解接口边界，准备给工程部下发子任务。" />
                  </Form.Item>
                  <Form.Item label="Todo 串" name="todos">
                    <Input placeholder="例如：调研|设计🔄|联调" />
                  </Form.Item>
                  <Button type="primary" icon={<ReloadOutlined />} htmlType="submit">
                    同步进展
                  </Button>
                </Form>
              ) : (
                <Alert type="info" showIcon message="当前账号没有推进任务的权限。" />
              ),
            },
            {
              key: "block",
              label: "阻塞",
              children: permissions.taskWrite ? (
                <Form
                  layout="vertical"
                  onFinish={(values) =>
                    onAction("/api/actions/task/block", {
                      taskId: task.id,
                      reason: values.reason,
                    })
                  }
                >
                  <Form.Item label="阻塞原因" name="reason" rules={[{ required: true, message: "请输入阻塞原因" }]}>
                    <TextArea rows={5} placeholder="例如：缺少线上环境访问权限，需要用户提供账号。" />
                  </Form.Item>
                  <Button danger icon={<ThunderboltOutlined />} htmlType="submit">
                    记录阻塞
                  </Button>
                </Form>
              ) : (
                <Alert type="info" showIcon message="当前账号没有阻塞治理权限。" />
              ),
            },
            {
              key: "done",
              label: "完成",
              children: permissions.taskWrite ? (
                <Form
                  layout="vertical"
                  onFinish={(values) =>
                    onAction("/api/actions/task/done", {
                      taskId: task.id,
                      summary: values.summary || "",
                      output: values.output || "",
                    })
                  }
                >
                  <Form.Item label="完成摘要" name="summary">
                    <TextArea rows={4} placeholder="例如：MVP 已发布到 staging，并完成冒烟验证。" />
                  </Form.Item>
                  <Form.Item label="产出路径" name="output">
                    <Input placeholder="/path/to/output 或交付链接" />
                  </Form.Item>
                  <Button type="primary" icon={<CheckCircleOutlined />} htmlType="submit">
                    标记完成
                  </Button>
                </Form>
              ) : (
                <Alert type="info" showIcon message="当前账号没有完成任务的权限。" />
              ),
            },
          ]}
        />
      ) : null}
    </Drawer>
  );
}

export default TaskDrawer;
