import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";

const { Password } = Input;
const { Paragraph, Text } = Typography;

function AdminView({
  dashboard,
  permissions,
  onRegisterInstance,
  onCreateUser,
  onCreateTenant,
  onBindTenantInstallation,
  onCreateTenantApiKey,
}) {
  const [latestApiKey, setLatestApiKey] = useState(null);
  const instances = dashboard.admin?.instances || [];
  const tenants = dashboard.admin?.tenants || [];
  const tenantApiKeys = dashboard.admin?.tenantApiKeys || [];
  const tenantOptions = useMemo(
    () => tenants.map((tenant) => ({ value: tenant.id, label: `${tenant.name} (${tenant.slug})` })),
    [tenants],
  );
  const installationOptions = useMemo(
    () => instances.map((item) => ({ value: item.openclawDir, label: `${item.label} · ${item.openclawDir}` })),
    [instances],
  );

  if (!(permissions.auditView || permissions.adminWrite)) {
    return <Alert type="warning" showIcon message="当前账号没有查看后台治理数据的权限。" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="登记实例" value={instances.length} suffix="套" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="租户数量" value={dashboard.admin?.tenantSummary?.total || 0} suffix="个" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="租户 API Keys" value={dashboard.admin?.tenantSummary?.apiKeys || 0} suffix="把" />
          </Card>
        </Col>
      </Row>

      {latestApiKey ? (
        <Alert
          type="success"
          showIcon
          message={`请立即保存 API Key：${latestApiKey}`}
          description="平台只会在创建成功这一刻展示一次完整 key，后续后台仅保留前缀与审计记录。"
        />
      ) : null}

      <Card title="SaaS 租户总览" extra={<Tag color="gold">Multi-tenant</Tag>}>
        <Table
          rowKey="id"
          dataSource={tenants}
          pagination={false}
          scroll={{ x: true }}
          columns={[
            { title: "租户", dataIndex: "name", render: (value, record) => <Space direction="vertical" size={0}><Text strong>{value}</Text><Text type="secondary">{record.slug}</Text></Space> },
            { title: "状态", dataIndex: "statusLabel", render: (value, record) => <Tag color={record.status === "active" ? "green" : "default"}>{value}</Tag> },
            { title: "实例", dataIndex: "installationCount" },
            { title: "活跃任务", dataIndex: "activeTasks" },
            { title: "Agent", dataIndex: "agentCount" },
            { title: "API Keys", dataIndex: "apiKeyCount" },
            { title: "主目录", dataIndex: "primaryOpenclawDir", ellipsis: true },
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}>
          <Card title="创建租户">
            {permissions.adminWrite ? (
              <Form layout="vertical" onFinish={onCreateTenant}>
                <Form.Item label="租户名称" name="name" rules={[{ required: true, message: "请输入租户名称" }]}>
                  <Input placeholder="例如：客户 A / Team North" />
                </Form.Item>
                <Form.Item label="租户标识" name="slug">
                  <Input placeholder="例如：team-north" />
                </Form.Item>
                <Form.Item label="主实例目录" name="primaryOpenclawDir">
                  <Input placeholder="/srv/openclaw/team-north" />
                </Form.Item>
                <Button type="primary" htmlType="submit">
                  保存租户
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号没有租户治理权限。" />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card title="绑定租户安装">
            {permissions.adminWrite ? (
              <Form layout="vertical" onFinish={onBindTenantInstallation}>
                <Form.Item label="租户" name="tenantId" rules={[{ required: true, message: "请选择租户" }]}>
                  <Select options={tenantOptions} placeholder="选择目标租户" />
                </Form.Item>
                <Form.Item label="OpenClaw 目录" name="openclawDir" rules={[{ required: true, message: "请输入目录" }]}>
                  <Select showSearch allowClear options={installationOptions} placeholder="/srv/openclaw/team-north" />
                </Form.Item>
                <Form.Item label="绑定角色" name="role" initialValue="primary">
                  <Select
                    options={[
                      { value: "primary", label: "Primary" },
                      { value: "secondary", label: "Secondary" },
                    ]}
                  />
                </Form.Item>
                <Form.Item label="显示名称" name="bindingLabel">
                  <Input placeholder="例如：客户 A - 生产环境" />
                </Form.Item>
                <Button type="primary" htmlType="submit">
                  绑定安装
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号没有实例治理权限。" />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card title="签发租户 API Key">
            {permissions.adminWrite ? (
              <Form
                layout="vertical"
                onFinish={async (values) => {
                  const response = await onCreateTenantApiKey(values);
                  setLatestApiKey(response?.apiKey?.rawKey || null);
                }}
              >
                <Form.Item label="租户" name="tenantId" rules={[{ required: true, message: "请选择租户" }]}>
                  <Select options={tenantOptions} placeholder="选择要发 key 的租户" />
                </Form.Item>
                <Form.Item label="Key 名称" name="name" rules={[{ required: true, message: "请输入 key 名称" }]}>
                  <Input placeholder="例如：ci-deploy / webhook-sync" />
                </Form.Item>
                <Form.Item
                  label="Scopes"
                  name="scopes"
                  initialValue={["tenant:read", "dashboard:read", "tasks:read", "tasks:write"]}
                >
                  <Select
                    mode="multiple"
                    options={[
                      { value: "tenant:read", label: "tenant:read" },
                      { value: "dashboard:read", label: "dashboard:read" },
                      { value: "agents:read", label: "agents:read" },
                      { value: "tasks:read", label: "tasks:read" },
                      { value: "tasks:write", label: "tasks:write" },
                    ]}
                  />
                </Form.Item>
                <Button type="primary" htmlType="submit">
                  创建 API Key
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号没有签发 API Key 的权限。" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="开放平台 API Keys">
        <Table
          rowKey="id"
          dataSource={tenantApiKeys}
          pagination={false}
          scroll={{ x: true }}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "租户", dataIndex: "tenantName" },
            { title: "前缀", dataIndex: "prefix" },
            { title: "状态", dataIndex: "status", render: (value) => <Tag color={value === "active" ? "green" : "default"}>{value}</Tag> },
            { title: "Scopes", dataIndex: "scopes", render: (value) => <Text>{(value || []).join(", ")}</Text> },
            { title: "最后使用", dataIndex: "lastUsedAt", render: (value) => value || "尚未使用" },
          ]}
        />
      </Card>

      <Card title="安装舰队">
        <Table
          rowKey="id"
          dataSource={instances}
          pagination={false}
          scroll={{ x: true }}
          columns={[
            { title: "实例", dataIndex: "label" },
            { title: "主题", dataIndex: "themeLabel" },
            { title: "状态", dataIndex: "statusLabel" },
            { title: "路由 Agent", dataIndex: "routerAgentId" },
            { title: "活跃任务", dataIndex: "activeTasks" },
            { title: "阻塞", dataIndex: "blockedTasks" },
            { title: "目录", dataIndex: "openclawDir", ellipsis: true },
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="登记实例">
            {permissions.adminWrite ? (
              <Form layout="vertical" onFinish={onRegisterInstance}>
                <Form.Item label="OpenClaw 目录" name="openclawDir" rules={[{ required: true, message: "请输入目录" }]}>
                  <Input placeholder="/Users/gaolei/.openclaw-another" />
                </Form.Item>
                <Form.Item label="显示名称" name="label">
                  <Input placeholder="例如：测试环境 / 客户 A" />
                </Form.Item>
                <Button type="primary" htmlType="submit">
                  登记实例
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号没有实例治理权限。" />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="创建席位">
            {permissions.adminWrite ? (
              <Form layout="vertical" onFinish={onCreateUser}>
                <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                  <Input />
                </Form.Item>
                <Form.Item label="显示名" name="displayName" rules={[{ required: true, message: "请输入显示名" }]}>
                  <Input />
                </Form.Item>
                <Form.Item label="角色" name="role" initialValue="operator">
                  <Select
                    options={[
                      { value: "owner", label: "Owner" },
                      { value: "operator", label: "Operator" },
                      { value: "viewer", label: "Viewer" },
                    ]}
                  />
                </Form.Item>
                <Form.Item label="初始密码" name="password" rules={[{ required: true, message: "请输入密码" }]}>
                  <Password autoComplete="new-password" />
                </Form.Item>
                <Button type="primary" htmlType="submit">
                  创建席位
                </Button>
              </Form>
            ) : (
              <Alert type="info" showIcon message="当前账号没有成员治理权限。" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="远程部署模式">
        <Paragraph style={{ marginBottom: 8 }}>
          Mission Control 现在支持用 Docker 交付成单个运行单元：前后端、OpenClaw CLI、状态卷和可选 PostgreSQL
          都已经有标准部署文件。
        </Paragraph>
        <Text code>docker compose up -d</Text>
        <Divider />
        <Text type="secondary">
          建议把每个租户的 OpenClaw 状态目录挂到独立卷，再用租户 API Key 接外部 CI/CD 和 webhook。
        </Text>
      </Card>

      <Card title="PostgreSQL 升级路径">
        <Paragraph style={{ marginBottom: 8 }}>
          当前控制平面运行内核仍以 SQLite 为默认，但已经补了 PostgreSQL 导出/迁移入口，适合把审计和历史任务数据转入更大的持久层。
        </Paragraph>
        <Text code>python3 bin/export_dashboard_postgres.py --dir ~/.openclaw --output ./dist/postgres-export</Text>
      </Card>
    </Space>
  );
}

export default AdminView;
