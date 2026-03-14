import { Button, Card, Form, Input, Space, Tabs, Tag, Typography } from "antd";

const { Title, Paragraph, Text } = Typography;
const { Password } = Input;

function LoginPage({ authMode, loading, onPasswordLogin, onTokenLogin, t }) {
  const [passwordForm] = Form.useForm();
  const [tokenForm] = Form.useForm();

  return (
    <div className="login-screen">
      <div className="login-hero">
        <div className="hero-headline">
          <Text className="section-kicker">{t("login.mission")}</Text>
          <Tag color="gold">{t("login.edition")}</Tag>
        </div>
        <Title level={1}>{t("login.heroTitle")}</Title>
        <Paragraph className="hero-summary">
          {t("login.heroSummary")}
        </Paragraph>

        <div className="hero-proofband">
          <div>
            <Text className="hero-proof-number">11</Text>
            <Text className="hero-proof-label">{t("login.proofAgents")}</Text>
          </div>
          <div>
            <Text className="hero-proof-number">API</Text>
            <Text className="hero-proof-label">{t("login.proofSeparation")}</Text>
          </div>
          <div>
            <Text className="hero-proof-number">Live</Text>
            <Text className="hero-proof-label">{t("login.proofLive")}</Text>
          </div>
        </div>

        <div className="login-points">
          <Card size="small" className="feature-card feature-card-accent">
            <Text strong>{t("login.cardUnified")}</Text>
            <Paragraph type="secondary">{t("login.cardUnifiedDesc")}</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text strong>{t("login.cardApi")}</Text>
            <Paragraph type="secondary">{t("login.cardApiDesc")}</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text strong>{t("login.cardLegacy")}</Text>
            <Paragraph type="secondary">{t("login.cardLegacyDesc")}</Paragraph>
          </Card>
        </div>
      </div>

      <Card className="login-card" bordered={false}>
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div>
            <Text className="section-kicker">{t("login.secureAccess")}</Text>
            <Title level={2}>{t("login.enter")}</Title>
            <Paragraph type="secondary">{t("login.enterSummary")}</Paragraph>
            <Tag color={authMode === "accounts" ? "processing" : "warning"}>
              {authMode === "accounts" ? t("login.accountsFirst") : authMode === "open" ? t("login.openMode") : t("login.tokenBootstrap")}
            </Tag>
          </div>

          <Tabs
            items={[
              {
                key: "password",
                label: t("login.passwordTab"),
                children: (
                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={(values) => onPasswordLogin(values.username, values.password)}
                  >
                    <Form.Item label={t("login.username")} name="username" rules={[{ required: true, message: t("login.usernameRequired") }]}>
                      <Input placeholder={t("login.usernamePlaceholder")} size="large" />
                    </Form.Item>
                    <Form.Item label={t("login.password")} name="password" rules={[{ required: true, message: t("login.passwordRequired") }]}>
                      <Password placeholder={t("login.passwordPlaceholder")} size="large" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                      {t("login.teamLogin")}
                    </Button>
                  </Form>
                ),
              },
              {
                key: "token",
                label: t("login.tokenTab"),
                children: (
                  <Form form={tokenForm} layout="vertical" onFinish={(values) => onTokenLogin(values.token)}>
                    <Form.Item label={t("login.token")} name="token" rules={[{ required: true, message: t("login.tokenRequired") }]}>
                      <Password placeholder={t("login.tokenPlaceholder")} size="large" />
                    </Form.Item>
                    <Button type="default" htmlType="submit" block size="large" loading={loading}>
                      {t("login.tokenLogin")}
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
