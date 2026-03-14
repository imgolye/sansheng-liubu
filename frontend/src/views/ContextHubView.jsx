import { useMemo, useState } from "react";
import { Alert, Button, Card, Col, Form, Input, List, Row, Select, Space, Statistic, Table, Typography } from "antd";
import { CloudDownloadOutlined, LikeOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

const FEEDBACK_LABELS = [
  "accurate",
  "well-structured",
  "helpful",
  "good-examples",
  "outdated",
  "inaccurate",
  "incomplete",
  "wrong-examples",
  "wrong-version",
  "poorly-structured",
];

function languageSummary(entry) {
  return safeArray(entry.languages)
    .map((item) => `${item.language || item.lang || "unknown"} ${item.recommendedVersion || ""}`.trim())
    .join(" · ");
}

function ContextHubView({ dashboard, permissions, onAction, t }) {
  const contextHub = dashboard.contextHub || {};
  const annotations = safeArray(contextHub.annotations?.items);
  const recommended = safeArray(contextHub.recommended);
  const cacheSources = safeArray(contextHub.cache?.sources);
  const [actionBusy, setActionBusy] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [fetchedDoc, setFetchedDoc] = useState(null);

  const annotationMap = useMemo(() => {
    const map = new Map();
    for (const item of annotations) {
      if (item?.id) {
        map.set(item.id, item);
      }
    }
    return map;
  }, [annotations]);

  async function run(key, path, payload, onSuccess) {
    setActionBusy(key);
    try {
      const response = await onAction(path, payload);
      if (onSuccess) {
        onSuccess(response?.result || response || {});
      }
      return response;
    } finally {
      setActionBusy("");
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("context.status")} value={contextHub.installed ? t("context.installed") : t("context.notInstalled")} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("context.version")} value={contextHub.version || "n/a"} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("context.annotations")} value={contextHub.annotations?.total || 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="workspace-card">
            <Statistic title={t("context.sources")} value={cacheSources.length || contextHub.config?.sourceCount || 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={9}>
          <Card
            title={t("context.controlCenter")}
            className="workspace-card"
            extra={permissions.adminWrite ? (
              <Space wrap>
                {!contextHub.installed ? (
                  <Button
                    type="primary"
                    icon={<CloudDownloadOutlined />}
                    loading={actionBusy === "install"}
                    onClick={() => run("install", "/api/actions/context-hub/install", {})}
                  >
                    {t("context.install")}
                  </Button>
                ) : null}
                <Button
                  icon={<ReloadOutlined />}
                  loading={actionBusy === "update"}
                  disabled={!contextHub.installed}
                  onClick={() => run("update", "/api/actions/context-hub/update", {})}
                >
                  {t("context.refreshRegistry")}
                </Button>
              </Space>
            ) : null}
          >
            <List
              dataSource={[
                { title: t("context.configPath"), detail: contextHub.config?.path || "n/a", status: contextHub.config?.exists ? "ready" : "warning" },
                { title: t("context.annotationPath"), detail: contextHub.annotations?.path || "n/a", status: "ready" },
                { title: t("context.sourcePolicy"), detail: contextHub.config?.sourcePolicy || "default", status: "ready" },
                { title: t("context.feedbackStatus"), detail: contextHub.config?.feedback || "default", status: "ready" },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<><Text strong>{item.title}</Text> {statusTag(item.status)}</>}
                    description={item.detail}
                  />
                </List.Item>
              )}
            />
            {!contextHub.installed ? (
              <Alert
                style={{ marginTop: 16 }}
                type="warning"
                showIcon
                message={t("context.installRequired")}
                description={t("context.installRequiredDesc")}
              />
            ) : (
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                showIcon
                message={t("context.whyItMatters")}
                description={t("context.whyItMattersDesc")}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card title={t("context.recommended")} className="workspace-card">
            <List
              dataSource={recommended}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key={`${item.query}-search`}
                      size="small"
                      icon={<SearchOutlined />}
                      loading={actionBusy === `search:${item.query}`}
                      onClick={() =>
                        run(`search:${item.query}`, "/api/actions/context-hub/search", { query: item.query, limit: 6 }, (result) => {
                          setSearchResults(safeArray(result.results));
                        })
                      }
                    >
                      {t("context.search")}
                    </Button>,
                    item.id ? (
                      <Button
                        key={`${item.id}-get`}
                        size="small"
                        loading={actionBusy === `get:${item.id}`}
                        onClick={() =>
                          run(`get:${item.id}`, "/api/actions/context-hub/get", { id: item.id }, (result) => {
                            setFetchedDoc(result);
                          })
                        }
                      >
                        {t("context.fetchDoc")}
                      </Button>
                    ) : null,
                  ]}
                >
                  <List.Item.Meta
                    title={<Text strong>{item.label}</Text>}
                    description={formatListText([item.query, item.id])}
                  />
                </List.Item>
              )}
            />
            {cacheSources.length ? (
              <Table
                style={{ marginTop: 16 }}
                size="small"
                rowKey={(item) => `${item.name}-${item.type}`}
                pagination={false}
                scroll={{ x: 720 }}
                dataSource={cacheSources}
                columns={[
                  { title: t("context.source"), dataIndex: "name", width: 140 },
                  { title: t("context.type"), dataIndex: "type", width: 120 },
                  { title: t("context.registry"), dataIndex: "hasRegistry", render: (value) => statusTag(value ? "ready" : "warning") },
                  { title: t("context.bundle"), dataIndex: "fullBundle", render: (value) => (value ? t("context.full") : t("context.incremental")) },
                  { title: t("context.lastUpdated"), dataIndex: "lastUpdated", ellipsis: true },
                ]}
              />
            ) : null}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={11}>
          <Card title={t("context.searchDocs")} className="workspace-card">
            <Form
              layout="vertical"
              initialValues={{ limit: 8 }}
              onFinish={(values) =>
                run("search", "/api/actions/context-hub/search", values, (result) => {
                  setSearchResults(safeArray(result.results));
                })
              }
            >
              <Row gutter={[12, 12]}>
                <Col xs={24} md={12}>
                  <Form.Item label={t("context.query")} name="query" rules={[{ required: true, message: t("context.queryRequired") }]}>
                    <Input placeholder="openai chat" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item label={t("context.lang")} name="lang">
                    <Select
                      allowClear
                      options={[
                        { value: "py", label: "py" },
                        { value: "js", label: "js" },
                        { value: "ts", label: "ts" },
                        { value: "go", label: "go" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item label={t("context.limit")} name="limit">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label={t("context.tags")} name="tags">
                <Input placeholder="openai,automation" />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={actionBusy === "search"} disabled={!contextHub.installed}>
                {t("context.search")}
              </Button>
            </Form>
            <Table
              style={{ marginTop: 16 }}
              size="small"
              rowKey="id"
              pagination={false}
              scroll={{ x: 820 }}
              dataSource={searchResults}
              locale={{ emptyText: t("context.emptySearch") }}
              columns={[
                { title: t("context.docId"), dataIndex: "id", width: 180 },
                { title: t("context.name"), dataIndex: "name", width: 140 },
                { title: t("context.languages"), render: (_, item) => languageSummary(item), ellipsis: true },
                { title: t("context.source"), dataIndex: "source", width: 120 },
                {
                  title: t("common.open"),
                  key: "action",
                  width: 120,
                  render: (_, item) => (
                    <Button
                      size="small"
                      loading={actionBusy === `get:${item.id}`}
                      onClick={() =>
                        run(`get:${item.id}`, "/api/actions/context-hub/get", { id: item.id }, (result) => {
                          setFetchedDoc(result);
                        })
                      }
                    >
                      {t("context.fetchDoc")}
                    </Button>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={13}>
          <Card title={t("context.docWorkbench")} className="workspace-card">
            <Form
              layout="vertical"
              onFinish={(values) =>
                run("get", "/api/actions/context-hub/get", values, (result) => {
                  setFetchedDoc(result);
                })
              }
            >
              <Row gutter={[12, 12]}>
                <Col xs={24} md={10}>
                  <Form.Item label={t("context.docId")} name="id" rules={[{ required: true, message: t("context.docIdRequired") }]}>
                    <Input placeholder="openai/chat" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={5}>
                  <Form.Item label={t("context.lang")} name="lang">
                    <Select allowClear options={[{ value: "py", label: "py" }, { value: "js", label: "js" }, { value: "ts", label: "ts" }]} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={9}>
                  <Form.Item label={t("context.files")} name="files">
                    <Input placeholder="references/errors.md" />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={actionBusy === "get"} disabled={!contextHub.installed}>
                  {t("context.fetchDoc")}
                </Button>
                <Button
                  loading={actionBusy === "get:full"}
                  disabled={!contextHub.installed}
                  onClick={() => {
                    const targetId = fetchedDoc?.id || searchResults[0]?.id || "";
                    if (!targetId) {
                      return;
                    }
                    run("get:full", "/api/actions/context-hub/get", { id: targetId, full: true }, (result) => {
                      setFetchedDoc(result);
                    });
                  }}
                >
                  {t("context.fetchFull")}
                </Button>
              </Space>
            </Form>

            {fetchedDoc ? (
              <Space direction="vertical" size={12} style={{ width: "100%", marginTop: 16 }}>
                <Alert
                  type="success"
                  showIcon
                  message={formatListText([fetchedDoc.id, fetchedDoc.type, fetchedDoc.annotation?.note || ""])}
                  description={formatListText([
                    fetchedDoc.version || "",
                    fetchedDoc.language || "",
                    safeArray(fetchedDoc.additionalFiles).length ? `${safeArray(fetchedDoc.additionalFiles).length} extra files` : "",
                  ])}
                />
                <pre className="openclaw-result-block">{fetchedDoc.content || t("context.emptyDoc")}</pre>
              </Space>
            ) : (
              <Alert style={{ marginTop: 16 }} type="info" showIcon message={t("context.docWorkbenchHint")} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title={t("context.annotationsCenter")} className="workspace-card">
            <Form
              layout="vertical"
              onFinish={(values) => run("annotate", "/api/actions/context-hub/annotate", values)}
            >
              <Form.Item label={t("context.docId")} name="id" rules={[{ required: true, message: t("context.docIdRequired") }]}>
                <Input placeholder="openai/chat" />
              </Form.Item>
              <Form.Item label={t("context.note")} name="note" rules={[{ required: true, message: t("context.noteRequired") }]}>
                <TextArea rows={4} placeholder={t("context.notePlaceholder")} />
              </Form.Item>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={actionBusy === "annotate"} disabled={!permissions.taskWrite}>
                  {t("context.saveAnnotation")}
                </Button>
                <Button
                  danger
                  loading={actionBusy === "clear-annotation"}
                  disabled={!permissions.taskWrite}
                  onClick={() => {
                    const targetId = fetchedDoc?.id || annotations[0]?.id || "";
                    if (!targetId) {
                      return;
                    }
                    run("clear-annotation", "/api/actions/context-hub/annotate", { id: targetId, clear: true });
                  }}
                >
                  {t("context.clearAnnotation")}
                </Button>
              </Space>
            </Form>

            <Table
              style={{ marginTop: 16 }}
              size="small"
              rowKey="id"
              pagination={false}
              scroll={{ x: 760 }}
              dataSource={annotations}
              locale={{ emptyText: t("context.noAnnotations") }}
              columns={[
                { title: t("context.docId"), dataIndex: "id", width: 180 },
                { title: t("context.note"), dataIndex: "note", ellipsis: true },
                { title: t("context.lastUpdated"), dataIndex: "updatedAt", ellipsis: true },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t("context.feedbackCenter")} className="workspace-card">
            <Form
              layout="vertical"
              initialValues={{ rating: "up", labels: ["helpful"] }}
              onFinish={(values) =>
                run("feedback", "/api/actions/context-hub/feedback", values)
              }
            >
              <Row gutter={[12, 12]}>
                <Col xs={24} md={12}>
                  <Form.Item label={t("context.docId")} name="id" rules={[{ required: true, message: t("context.docIdRequired") }]}>
                    <Input placeholder="openai/chat" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={t("context.rating")} name="rating">
                    <Select options={[{ value: "up", label: "up" }, { value: "down", label: "down" }]} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label={t("context.labels")} name="labels">
                <Select mode="multiple" options={FEEDBACK_LABELS.map((label) => ({ value: label, label }))} />
              </Form.Item>
              <Form.Item label={t("context.comment")} name="comment">
                <TextArea rows={3} placeholder={t("context.commentPlaceholder")} />
              </Form.Item>
              <Space wrap>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<LikeOutlined />}
                  loading={actionBusy === "feedback"}
                  disabled={!permissions.adminWrite || !contextHub.installed}
                >
                  {t("context.sendFeedback")}
                </Button>
                <Text type="secondary">{t("context.feedbackHint")}</Text>
              </Space>
            </Form>
            <List
              style={{ marginTop: 16 }}
              dataSource={safeArray(contextHub.commands)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Text strong>{item.label}</Text>}
                    description={formatListText([item.description, item.command])}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {fetchedDoc?.id && annotationMap.get(fetchedDoc.id)?.note ? (
        <Alert
          type="warning"
          showIcon
          message={t("context.localMemory")}
          description={annotationMap.get(fetchedDoc.id)?.note}
        />
      ) : null}
    </Space>
  );
}

export default ContextHubView;
