import { Component } from "react";
import { Button, Card, Result } from "antd";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Card>
          <Result
            status="error"
            title="此模块出错"
            subTitle={this.state.error?.message || "渲染时发生未知错误。"}
            extra={
              <Button type="primary" onClick={() => this.setState({ hasError: false, error: null })}>
                重试
              </Button>
            }
          />
        </Card>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
