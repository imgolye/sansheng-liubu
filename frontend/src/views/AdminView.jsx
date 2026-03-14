import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Statistic, Table } from "antd";

const { Password } = Input;

function AdminView({ dashboard, permissions, onRegisterInstance, onCreateUser }) {
  if (!(permissions.auditView || permissions.adminWrite)) {
    return <Alert type="warning" showIcon message="当前账号没有查看后台治理数据的权限。" />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="登记实例" value={dashboard.admin?.instances?.length || 0} suffix="套" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="活跃任务" value={dashboard.admin?.instanceSummary?.activeTasks || 0} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="阻塞任务" value={dashboard.admin?.instanceSummary?.blockedTasks || 0} suffix="条" />
          </Card>
        </Col>
      </Row>

      <Card title="安装舰队">
        <Table
          rowKey="id"
          dataSource={dashboard.admin?.instances || []}
          pagination={false}
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
                  <Password />
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
    </Space>
  );
}

export default AdminView;
