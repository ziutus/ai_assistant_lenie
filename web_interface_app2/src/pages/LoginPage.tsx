import React, { useContext, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Container, Form, Spinner } from 'react-bootstrap';
import { AuthContext } from '../context/AuthContext';
import { DEFAULT_API_URL } from '../services/storage';

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useContext(AuthContext);

  const [username, setUsername] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [showApiUrl, setShowApiUrl] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !apiKey.trim()) {
      setError('Username and API key are required.');
      return;
    }

    setIsLoading(true);
    try {
      await login(username.trim(), apiKey.trim(), apiUrl.trim());
      navigate('/', { replace: true });
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as { response?: { status?: number } }).response;
        if (resp?.status === 403 || resp?.status === 401) {
          setError('Invalid credentials. Check your API key.');
        } else {
          setError('Connection failed. Check the API URL and try again.');
        }
      } else if (err && typeof err === 'object' && 'code' in err) {
        const code = (err as { code?: string }).code;
        if (code === 'ECONNABORTED' || code === 'ERR_NETWORK') {
          setError('Connection timed out. Check the API URL.');
        } else {
          setError('Connection failed. Check the API URL and try again.');
        }
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container className="d-flex align-items-center justify-content-center min-vh-100">
      <Card style={{ width: '100%', maxWidth: '420px' }}>
        <Card.Body className="p-4">
          <h3 className="text-center mb-4">Lenie AI</h3>
          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3" controlId="username">
              <Form.Label>Username</Form.Label>
              <Form.Control
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                autoFocus
                disabled={isLoading}
              />
            </Form.Group>

            <Form.Group className="mb-3" controlId="apiKey">
              <Form.Label>API Key</Form.Label>
              <Form.Control
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter API key"
                disabled={isLoading}
              />
            </Form.Group>

            {showApiUrl ? (
              <Form.Group className="mb-3" controlId="apiUrl">
                <Form.Label>API URL</Form.Label>
                <Form.Control
                  type="text"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  disabled={isLoading}
                />
              </Form.Group>
            ) : (
              <div className="mb-3">
                <Button
                  variant="link"
                  size="sm"
                  className="p-0"
                  onClick={() => setShowApiUrl(true)}
                >
                  Advanced settings
                </Button>
              </div>
            )}

            {error && <Alert variant="danger">{error}</Alert>}

            <Button type="submit" variant="primary" className="w-100" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Connecting...
                </>
              ) : (
                'Login'
              )}
            </Button>
          </Form>
        </Card.Body>
      </Card>
    </Container>
  );
};

export default LoginPage;
