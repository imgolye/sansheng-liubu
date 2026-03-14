import { Button, Card, Form, Input, Space, Tabs, Tag, Typography } from "antd";

const { Title, Paragraph, Text } = Typography;
const { Password } = Input;

function LoginPage({ authMode, loading, onPasswordLogin, onTokenLogin }) {
  const [passwordForm] = Form.useForm();
  const [tokenForm] = Form.useForm();

  return (
    <div className="login-screen">
      <div className="login-hero">
        <div className="hero-headline">
          <Text className="section-kicker">Mission Control</Text>
          <Tag color="gold">Commercial Edition</Tag>
        </div>
        <Title level={1}>把多 Agent 协同，做成能运营、能治理、能成交的产品。</Title>
        <Paragraph className="hero-summary">
          现在打开的不是实验面板，而是一套面向业务负责人的控制平面。你可以在同一个产品里看到协同状态、推进任务、
          直接对话、切换主题，并持续治理团队与安装实例。
        </Paragraph>

        <div className="hero-proofband">
          <div>
            <Text className="hero-proof-number">11</Text>
            <Text className="hero-proof-label">协作 Agent</Text>
          </div>
          <div>
            <Text className="hero-proof-number">API</Text>
            <Text className="hero-proof-label">前后端分离</Text>
          </div>
          <div>
            <Text className="hero-proof-number">Live</Text>
            <Text className="hero-proof-label">任务与会话运营</Text>
          </div>
        </div>

        <div className="login-points">
          <Card size="small" className="feature-card feature-card-accent">
            <Text strong>统一经营视图</Text>
            <Paragraph type="secondary">协同、交付、会话、技能、OpenClaw 运行态放进同一条运营视线。</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text strong>API-first Product Core</Text>
            <Paragraph type="secondary">账号、会话状态、任务动作、主题切换和治理接口全部独立输出。</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text strong>渐进替换旧入口</Text>
            <Paragraph type="secondary">新版产品壳走独立前端，旧版 `/legacy` 入口仍保留，迁移不会硬切。</Paragraph>
          </Card>
        </div>
      </div>

      <Card className="login-card" bordered={false}>
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div>
            <Text className="section-kicker">Secure Access</Text>
            <Title level={2}>进入 Mission Control</Title>
            <Paragraph type="secondary">优先使用团队账号；Owner Token 只保留给初始化和紧急接管。</Paragraph>
            <Tag color={authMode === "accounts" ? "processing" : "warning"}>
              {authMode === "accounts" ? "团队账号优先" : authMode === "open" ? "开放模式" : "Token Bootstrap"}
            </Tag>
          </div>

          <Tabs
            items={[
              {
                key: "password",
                label: "团队账号",
                children: (
                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={(values) => onPasswordLogin(values.username, values.password)}
                  >
                    <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                      <Input placeholder="owner / alice@company" size="large" />
                    </Form.Item>
                    <Form.Item label="密码" name="password" rules={[{ required: true, message: "请输入密码" }]}>
                      <Password placeholder="输入团队账号密码" size="large" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                      团队登录
                    </Button>
                  </Form>
                ),
              },
              {
                key: "token",
                label: "Owner Token",
                children: (
                  <Form form={tokenForm} layout="vertical" onFinish={(values) => onTokenLogin(values.token)}>
                    <Form.Item label="Token" name="token" rules={[{ required: true, message: "请输入 Owner Token" }]}>
                      <Password placeholder="输入本地 dashboard token" size="large" />
                    </Form.Item>
                    <Button type="default" htmlType="submit" block size="large" loading={loading}>
                      使用 Token 进入
                    </Button>
                  </Form>
                ),
              },
            ]}
          />
        </Space>
      </Card>
    </div>
  );
}

export default LoginPage;
