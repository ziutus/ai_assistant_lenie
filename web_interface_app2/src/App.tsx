import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './components/RequireAuth';
import LoginPage from './pages/LoginPage';
import ThemeLayout from './ThemeLayout';

// Pages from purchased layout
import Home from 'Pages/Home/index';
import CommunityFeed from 'Pages/CommunityFeed';
import CommunityDetails from 'Pages/CommunityDetails';
import ManageSubscription from 'Pages/ManageSubscription';
import Chatbot from 'Pages/Chatbot';
import ImageGenerator from 'Pages/ImageGenerator';
import VoiceGenerator from 'Pages/VoiceGenerator';
import Faq from 'Pages/Settings/Faq';

const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <ThemeLayout>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/community-feed" element={<CommunityFeed />} />
                <Route path="/community-details" element={<CommunityDetails />} />
                <Route path="/manage-subscription" element={<ManageSubscription />} />
                <Route path="/chatbot" element={<Chatbot />} />
                <Route path="/image-generator" element={<ImageGenerator />} />
                <Route path="/voicegenerator" element={<VoiceGenerator />} />
                <Route path="/faq" element={<Faq />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ThemeLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
};

export default App;
