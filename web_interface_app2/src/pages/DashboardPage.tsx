import React, { useContext } from 'react';
import { Button, Container } from 'react-bootstrap';
import { AuthContext } from '../context/AuthContext';

const DashboardPage: React.FC = () => {
  const { auth, logout } = useContext(AuthContext);

  return (
    <Container className="py-5">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h2>Dashboard</h2>
        <Button variant="outline-secondary" size="sm" onClick={logout}>
          Logout
        </Button>
      </div>
      <p>Welcome, {auth?.username}!</p>
      <p className="text-muted">Connected to: {auth?.apiUrl}</p>
      <hr />
      <h5>Layout Preview</h5>
      <p className="text-muted">
        The purchased layout uses BrowserRouter and requires serving from root path.
      </p>
      <Button
        variant="primary"
        onClick={() => window.open('/legacy/index.html', '_blank')}
      >
        Open Layout Preview
      </Button>
    </Container>
  );
};

export default DashboardPage;
