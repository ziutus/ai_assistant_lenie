import React from "react";
import Layout from "./modules/shared/components/Layout/Layout";
import Authorization from "./modules/shared/components/Authorization/authorization";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import ContentGroupsPanel from "./modules/shared/components/ContentGroupsPanel/ContentGroupsPanel";
import Link from "./modules/shared/pages/link";
import Webpage from "./modules/shared/pages/webpage";
import Youtube from "./modules/shared/pages/youtube";
import Movie from "./modules/shared/pages/movie";
import Email from "./modules/shared/pages/email";
import SocialMediaPost from "./modules/shared/pages/socialMediaPost";
import Search from "./modules/shared/pages/search";
import List from "./modules/shared/pages/list";
import UploadFile from "./modules/shared/pages/file";
import Connect from "./modules/shared/pages/connect";
import Chunks from "./modules/shared/pages/chunks";
import Read from "./modules/shared/pages/read";
import Persons from "./modules/shared/pages/persons";
import PersonsReview from "./modules/shared/pages/personsReview";
import Sources from "./modules/shared/pages/sources";
import InformationSources from "./modules/shared/pages/informationSources";
import LlmCosts from "./modules/shared/pages/llmCosts";
import ServiceStatus from "./modules/shared/pages/serviceStatus";
import Stats from "./modules/shared/pages/stats";
import Feeds from "./modules/shared/pages/feeds";
import FeedReview from "./modules/shared/pages/feedReview";
import LlmAnalysis from "./modules/shared/pages/llmAnalysis";
import Jobs from "./modules/shared/pages/jobs";
import Scheduler from "./modules/shared/pages/scheduler";
import Entities from "./modules/shared/pages/entities";
import { AuthorizationContext } from "./modules/shared/context/authorizationContext";

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { apiKey } = React.useContext(AuthorizationContext);
  if (!apiKey) {
    return <Navigate to="/connect" replace />;
  }
  return <>{children}</>;
};

const DocumentEditorWithGroups: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { id } = useParams();
  return <>{id && <ContentGroupsPanel documentId={id} />}{children}</>;
};

function App() {
  const location = useLocation();
  const hideAuthorizationBar = location.pathname.startsWith("/read/");

  return (
    <Routes>
      <Route path="/connect" element={<Connect />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <div className="App">
                {!hideAuthorizationBar && <Authorization />}
                <Routes>
                  <Route path="/" element={<Navigate to="/list" />} />
                  <Route path="/webpage/:id?" element={<DocumentEditorWithGroups><Webpage /></DocumentEditorWithGroups>} />
                  <Route path="/text/:id?" element={<DocumentEditorWithGroups><Webpage /></DocumentEditorWithGroups>} />
                  <Route path="/link/:id?" element={<DocumentEditorWithGroups><Link /></DocumentEditorWithGroups>} />
                  <Route path="/movie/:id?" element={<DocumentEditorWithGroups><Movie /></DocumentEditorWithGroups>} />
                  <Route path="/youtube/:id?" element={<DocumentEditorWithGroups><Youtube /></DocumentEditorWithGroups>} />
                  <Route path="/email/:id?" element={<DocumentEditorWithGroups><Email /></DocumentEditorWithGroups>} />
                  <Route path="/social_media_post/:id?" element={<DocumentEditorWithGroups><SocialMediaPost /></DocumentEditorWithGroups>} />
                  <Route path="/chunks/:id" element={<Chunks />} />
                  <Route path="/read/:id" element={<Read />} />
                  <Route path="/entities/:id" element={<Entities />} />
                  <Route path="/list" element={<List />} />
                  <Route path="/persons/:id?" element={<Persons />} />
                  <Route path="/persons-review" element={<PersonsReview />} />
                  <Route path="/sources" element={<Sources />} />
                  <Route path="/information-sources" element={<InformationSources />} />
                  <Route path="/llm-costs" element={<LlmCosts />} />
                  <Route path="/service-status" element={<ServiceStatus />} />
                  <Route path="/stats" element={<Stats />} />
                  <Route path="/feeds" element={<Feeds />} />
                  <Route path="/feed-review" element={<FeedReview />} />
                  <Route path="/llm-analysis" element={<LlmAnalysis />} />
                  <Route path="/jobs" element={<Jobs />} />
                  <Route path="/scheduler" element={<Scheduler />} />
                  <Route path="/search" element={<Search />} />
                  <Route path="/upload-file" element={<UploadFile />} />
                  <Route path="*" element={<p>404</p>} />
                </Routes>
              </div>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default App;
