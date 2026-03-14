import { useState } from "react";
import { Alert, Button, Card, Col, Form, Input, List, Row, Select, Space, Statistic, Table, Typography } from "antd";
import { LinkOutlined, PlayCircleOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const DEFAULT_PLAN = JSON.stringify(
  [
    { action: "open", url: "https://example.com" },
    { action: "wait", time: 1200 },
    { action: "snapshot", format: "ai", limit: 80 },
  ],
  null,
  2,
);

function OpenClawView({ dashboard, permissions, onAction, t }) {
  const openclaw = dashboard.openclaw || {};
  const gatewayChannels = safeArray(openclaw.gateway?.channels);
  const browserProfiles = safeArray(openclaw.browser?.profiles);
  const recommendedProfiles = safeArray(openclaw.browser?.recommendedProfiles);
  const skillsWarnings = safeArray(openclaw.nativeSkills?.warnings);
  const skillsCheck = openclaw.nativeSkills?.check || {};
  const missingRequirements = safeArray(skillsCheck.missingRequirements).slice(0, 10);
  const agentParams = safeArray(openclaw.agentParams);
  const [actionResult, setActionResult] = useState("");

  async function run(path, payload, successMessage = "") {
    const response = await onAction(path, payload, successMessage);
    const result = response?.result;
    if (typeof result?.output === "string" && result.output) {
      setActionResult(result.output);
    } else if (Array.isArray(result?.results) && result.results.length) {
      setActionResult(result.results.map((item) => `#${item.index} ${item.action}\n${item.output || ""}`.trim()).join("\n\n"));
    } else if (typeof result?.path?.output === "string" && result.path.output) {
      setActionResult(result.path.output);
    } else {
      setActionResult(JSON.stringify(result || response || {}, null, 2));
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.version")} value={openclaw.version?.release || "unknown"} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.nativeSkills")} value={openclaw.nativeSkills?.total || 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.rpcStatus")} value={openclaw.gateway?.rpc?.ok ? t("openclaw.ready") : t("openclaw.attention")} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("openclaw.browserAttach")} value={openclaw.browser?.running ? t("openclaw.ready") : t("openclaw.idle")} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title={t("openclaw.compatibility")} className="workspace-card">
            <List
              dataSource={safeArray(openclaw.compatibility)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<><Text strong>{item.title}</Text> {statusTag(item.status)}</>}
                    description={formatListText([item.body, item.meta])}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card
            title={t("openclaw.gateway")}
            className="workspace-card"
            extra={permissions.adminWrite ? (
              <Space wrap>
                <Button icon={<PlayCircleOutlined />} onClick={() => run("/api/actions/openclaw/gateway/start", {})}>
                  {t("openclaw.startGateway")}
                </Button>
                <Button icon={<ReloadOutlined />} onClick={() => run("/api/actions/openclaw/gateway/restart", {})}>
                  {t("openclaw.restartGateway")}
                </Button>
              </Space>
            ) : null}
          >
            <Table
              size="small"
              rowKey="title"
              pagination={false}
              scroll={{ x: 760 }}
              dataSource={gatewayChannels}
              columns={[
                { title: t("openclaw.channel"), dataIndex: "title" },
                { title: t("openclaw.config"), dataIndex: "meta" },
                { title: t("openclaw.running"), dataIndex: "running", render: (value) => (value ? statusTag("ready") : statusTag("warning")) },
                { title: t("openclaw.detail"), dataIndex: "detail", ellipsis: true },
              ]}
            />
            <Alert
              style={{ marginTop: 16 }}
              type={openclaw.gateway?.rpc?.ok ? "success" : "warning"}
              showIcon
              message={t("openclaw.rpcHealth")}
              description={formatListText([
                openclaw.gateway?.rpc?.ok ? t("openclaw.rpcOk") : (openclaw.gateway?.rpc?.error || t("openclaw.rpcFailed")),
                openclaw.gateway?.rpc?.probeUrl || openclaw.gateway?.rpc?.url || "",
              ])}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card
            title={t("openclaw.browserPanel")}
            className="workspace-card"
            extra={permissions.adminWrite ? (
              <Space wrap>
                <Button onClick={() => run("/api/actions/openclaw/browser/start", {})}>
                  {t("openclaw.startBrowser")}
                </Button>
                <Button icon={<SafetyCertificateOutlined />} onClick={() => run("/api/actions/openclaw/browser/extension/install", {})}>
                  {t("openclaw.installExtension")}
                </Button>
              </Space>
            ) : null}
          >
            <List
              dataSource={recommendedProfiles.length ? recommendedProfiles : browserProfiles}
              locale={{ emptyText: t("openclaw.noBrowserProfiles") }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<><Text strong>{item.title || item.name}</Text> {statusTag(item.available || item.running ? "ready" : "warning")}</>}
                    description={formatListText([
                      item.detail || "",
                      item.available ? t("openclaw.profileAvailable") : t("openclaw.profileMissing"),
                    ])}
                  />
                </List.Item>
              )}
            />
            {permissions.adminWrite ? (
              <Form
                layout="vertical"
                style={{ marginTop: 16 }}
                initialValues={{ driver: "openclaw", color: "#B55A2A" }}
                onFinish={(values) => run("/api/actions/openclaw/browser/profile/create", values)}
              >
                <Row gutter={[12, 12]}>
                  <Col xs={24} md={10}>
                    <Form.Item label={t("openclaw.profileName")} name="name" rules={[{ required: true, message: t("openclaw.profileNameRequired") }]}>
                      <Input placeholder="chrome-relay" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item label={t("openclaw.profileDriver")} name="driver">
                      <Select options={[
                        { value: "openclaw", label: "openclaw" },
                        { value: "extension", label: "extension" },
                        { value: "existing-session", label: "existing-session" },
                      ]} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item label={t("openclaw.profileColor")} name="color">
                      <Input placeholder="#B55A2A" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label={t("openclaw.cdpUrl")} name="cdpUrl">
                  <Input placeholder="http://127.0.0.1:9222" />
                </Form.Item>
                <Button type="primary" htmlType="submit">{t("openclaw.createProfile")}</Button>
              </Form>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t("openclaw.browserWorkbench")} className="workspace-card">
            {permissions.adminWrite ? (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Form layout="vertical" onFinish={(values) => run("/api/actions/openclaw/browser/open", values)}>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={16}>
                      <Form.Item label={t("openclaw.openUrl")} name="url" rules={[{ required: true, message: t("openclaw.urlRequired") }]}>
                        <Input placeholder="https://example.com" prefix={<LinkOutlined />} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item label={t("openclaw.browserProfile")} name="profile">
                        <Select allowClear options={browserProfiles.map((item) => ({ value: item.name, label: item.name }))} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Button type="primary" htmlType="submit">{t("openclaw.openInBrowser")}</Button>
                </Form>

                <Form layout="vertical" onFinish={(values) => run("/api/actions/openclaw/browser/snapshot", values)}>
                  <Row gutter={[12, 12]}>
                    <Col xs={24} md={10}>
                      <Form.Item label={t("openclaw.browserProfile")} name="profile">
                        <Select allowClear options={browserProfiles.map((item) => ({ value: item.name, label: item.name }))} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item label={t("openclaw.snapshotSelector")} name="selector">
                        <Input placeholder="#app main" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={6}>
                      <Form.Item label={t("openclaw.snapshotLimit")} name="limit" initialValue={120}>
                        <Input />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Button htmlType="submit">{t("openclaw.captureSnapshot")}</Button>
                </Form>

                <Form
                  layout="vertical"
                  initialValues={{ plan: DEFAULT_PLAN }}
                  onFinish={(values) => {
                    let steps = [];
                    try {
                      steps = JSON.parse(values.plan || "[]");
                    } catch {
                      throw new Error(t("openclaw.planJsonInvalid"));
                    }
                    return run("/api/actions/openclaw/browser/plan", { profile: values.profile, steps });
                  }}
                >
                  <Form.Item label={t("openclaw.browserProfile")} name="profile">
                    <Select allowClear options={browserProfiles.map((item) => ({ value: item.name, label: item.name }))} />
                  </Form.Item>
                  <Form.Item label={t("openclaw.planTitle")} name="plan">
                    <TextArea rows={8} />
                  </Form.Item>
                  <Button htmlType="submit">{t("openclaw.runPlan")}</Button>
                </Form>
              </Space>
            ) : (
              <Alert type="info" showIcon message={t("openclaw.ownerOnlyActions")} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title={t("openclaw.skillsWarnings")} className="workspace-card">
            <Paragraph type="secondary">
              {formatListText([
                `${skillsCheck.summary?.eligible || 0} ${t("openclaw.skillsEligible")}`,
                `${skillsCheck.summary?.missingRequirements || 0} ${t("openclaw.skillsMissing")}`,
              ])}
            </Paragraph>
            <List
              dataSource={missingRequirements}
              locale={{ emptyText: t("openclaw.noSkillWarnings") }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<><Text strong>{item.name}</Text> {statusTag("warning")}</>}
                    description={formatListText([
                      safeArray(item.missing?.bins).join(", "),
                      safeArray(item.missing?.env).join(", "),
                      safeArray(item.missing?.config).join(", "),
                    ])}
                  />
                </List.Item>
              )}
            />
            {skillsWarnings.length ? (
              <Alert style={{ marginTop: 16 }} type="warning" showIcon message={t("openclaw.skillsRootWarnings")} description={skillsWarnings.slice(0, 3).join(" · ")} />
            ) : null}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t("openclaw.agentParams")} className="workspace-card">
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              scroll={{ x: 760 }}
              dataSource={agentParams}
              locale={{ emptyText: t("openclaw.noAgentParams") }}
              columns={[
                { title: t("openclaw.agentId"), dataIndex: "id", width: 140 },
                { title: t("openclaw.configParams"), dataIndex: "summary", ellipsis: true },
                { title: t("openclaw.workspacePath"), dataIndex: "workspace", ellipsis: true },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {actionResult ? (
        <Card title={t("openclaw.actionResult")} className="workspace-card">
          <pre className="openclaw-result-block">{actionResult}</pre>
        </Card>
      ) : null}
    </Space>
  );
}

export default OpenClawView;
