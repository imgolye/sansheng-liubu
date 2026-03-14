import { Button, Card, Result } from "antd";
import { Component } from "react";

class ViewErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    if (this.props.onError) {
      this.props.onError(error);
    }
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Card className="workspace-card">
          <Result
            status="error"
            title={this.props.title}
            subTitle={this.props.description}
            extra={(
              <Button type="primary" onClick={() => this.setState({ hasError: false })}>
                {this.props.retryLabel}
              </Button>
            )}
          />
        </Card>
      );
    }
    return this.props.children;
  }
}

export default ViewErrorBoundary;
