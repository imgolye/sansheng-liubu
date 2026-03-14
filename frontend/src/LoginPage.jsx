import { Button, Card, Form, Input, Space, Tabs, Tag, Typography } from "antd";

const { Title, Paragraph, Text } = Typography;
const { Password } = Input;

function LoginPage({ authMode, loading, onPasswordLogin, onTokenLogin, t }) {
  const [passwordForm] = Form.useForm();
  const [tokenForm] = Form.useForm();

  return (
    <div className="login-screen">
      <section className="login-hero">
        <div className="hero-headline">
          <Text className="section-kicker">{t("login.mission")}</Text>
          <Tag color="gold">{t("login.edition")}</Tag>
          <Tag className="login-hero-tag">{t("login.positioning")}</Tag>
        </div>

        <Title level={1}>{t("login.heroTitle")}</Title>
        <Paragraph className="hero-summary">{t("login.heroSummary")}</Paragraph>

        <div className="hero-proofband">
          <div>
            <Text className="hero-proof-number">{t("login.proofAgentsValue")}</Text>
            <Text className="hero-proof-label">{t("login.proofAgents")}</Text>
          </div>
          <div>
            <Text className="hero-proof-number">{t("login.proofSeparationValue")}</Text>
            <Text className="hero-proof-label">{t("login.proofSeparation")}</Text>
          </div>
          <div>
            <Text className="hero-proof-number">{t("login.proofLiveValue")}</Text>
            <Text className="hero-proof-label">{t("login.proofLive")}</Text>
          </div>
        </div>

        <div className="login-outcome-grid">
          <Card size="small" className="feature-card feature-card-accent">
            <Text className="feature-card-kicker">{t("login.outcome1Eyebrow")}</Text>
            <Text strong>{t("login.outcome1Title")}</Text>
            <Paragraph type="secondary">{t("login.outcome1Desc")}</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text className="feature-card-kicker">{t("login.outcome2Eyebrow")}</Text>
            <Text strong>{t("login.outcome2Title")}</Text>
            <Paragraph type="secondary">{t("login.outcome2Desc")}</Paragraph>
          </Card>
          <Card size="small" className="feature-card">
            <Text className="feature-card-kicker">{t("login.outcome3Eyebrow")}</Text>
            <Text strong>{t("login.outcome3Title")}</Text>
            <Paragraph type="secondary">{t("login.outcome3Desc")}</Paragraph>
          </Card>
        </div>

        <div className="login-market-grid">
          <Card className="login-market-card login-market-card-primary" bordered={false}>
            <Text className="section-kicker">{t("login.marketTitle")}</Text>
            <Title level={3}>{t("login.marketHeadline")}</Title>
            <div className="login-bullet-list">
              <div>
                <Text strong>{t("login.marketPoint1Title")}</Text>
                <Paragraph type="secondary">{t("login.marketPoint1Desc")}</Paragraph>
              </div>
              <div>
                <Text strong>{t("login.marketPoint2Title")}</Text>
                <Paragraph type="secondary">{t("login.marketPoint2Desc")}</Paragraph>
              </div>
              <div>
                <Text strong>{t("login.marketPoint3Title")}</Text>
                <Paragraph type="secondary">{t("login.marketPoint3Desc")}</Paragraph>
              </div>
            </div>
          </Card>

          <div className="login-trust-stack">
            <Card className="login-trust-card" bordered={false}>
              <Text className="section-kicker">{t("login.trustTitle")}</Text>
              <div className="login-trust-list">
                <div>
                  <Text strong>{t("login.trustPoint1Title")}</Text>
                  <Paragraph type="secondary">{t("login.trustPoint1Desc")}</Paragraph>
                </div>
                <div>
                  <Text strong>{t("login.trustPoint2Title")}</Text>
                  <Paragraph type="secondary">{t("login.trustPoint2Desc")}</Paragraph>
                </div>
                <div>
                  <Text strong>{t("login.trustPoint3Title")}</Text>
                  <Paragraph type="secondary">{t("login.trustPoint3Desc")}</Paragraph>
                </div>
              </div>
            </Card>

            <Card className="login-trust-card login-trust-card-quote" bordered={false}>
              <Text className="section-kicker">{t("login.quoteEyebrow")}</Text>
              <Paragraph className="login-quote">{t("login.quoteText")}</Paragraph>
              <Text type="secondary">{t("login.quoteMeta")}</Text>
            </Card>
          </div>
        </div>
      </section>

      <section className="login-access-shell">
        <Card className="login-card" bordered={false}>
          <Space direction="vertical" size={20} style={{ width: "100%" }}>
            <div className="login-access-head">
              <div>
                <Text className="section-kicker">{t("login.secureAccess")}</Text>
                <Title level={2}>{t("login.enter")}</Title>
                <Paragraph type="secondary">{t("login.enterSummary")}</Paragraph>
              </div>
              <div className="login-access-badges">
                <Tag color={authMode === "accounts" ? "processing" : authMode === "open" ? "success" : "warning"}>
                  {authMode === "accounts" ? t("login.accountsFirst") : authMode === "open" ? t("login.openMode") : t("login.tokenBootstrap")}
                </Tag>
                <Tag>{t("login.localControl")}</Tag>
              </div>
            </div>

            <div className="login-access-strip">
              <div>
                <Text className="login-strip-label">{t("login.accessPointTitle")}</Text>
                <Text className="login-strip-value">{t("login.accessPointValue")}</Text>
              </div>
              <div>
                <Text className="login-strip-label">{t("login.governanceTitle")}</Text>
                <Text className="login-strip-value">{t("login.governanceValue")}</Text>
              </div>
            </div>

            <Tabs
              items={[
                {
                  key: "password",
                  label: t("login.passwordTab"),
                  children: (
                    <Form form={passwordForm} layout="vertical" onFinish={(values) => onPasswordLogin(values.username, values.password)}>
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

            <div className="login-assurance-panel">
              <div>
                <Text strong>{t("login.assurance1Title")}</Text>
                <Paragraph type="secondary">{t("login.assurance1Desc")}</Paragraph>
              </div>
              <div>
                <Text strong>{t("login.assurance2Title")}</Text>
                <Paragraph type="secondary">{t("login.assurance2Desc")}</Paragraph>
              </div>
            </div>
          </Space>
        </Card>

        <div className="login-access-notes">
          <Card className="login-note-card" bordered={false}>
            <Text className="section-kicker">{t("login.noteTitle")}</Text>
            <Paragraph>{t("login.noteDesc")}</Paragraph>
          </Card>
          <Card className="login-note-card login-note-card-accent" bordered={false}>
            <Text className="section-kicker">{t("login.note2Title")}</Text>
            <Paragraph>{t("login.note2Desc")}</Paragraph>
          </Card>
        </div>
      </section>
    </div>
  );
}

export default LoginPage;
