import { useState, useEffect } from 'react';
import ProjectList from './components/ProjectList';
import Workspace from './components/Workspace';
import StandalonePage from './StandalonePage';
import { listProjects, createProject, deleteProject } from './api/client';

export default function App() {
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [standalone, setStandalone] = useState(false);

  const refreshProjects = async () => {
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (e) {
      // If backend is unreachable, switch to standalone YouTube-only mode
      console.error('Backend not available, switching to standalone mode');
      setStandalone(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refreshProjects(); }, []);

  if (standalone) return <StandalonePage />;

  const handleCreate = async (name) => {
    try {
      await createProject(name);
      await refreshProjects();
      setCurrentProject(name);
    } catch (e) {
      alert(`Failed to create project: ${e.message}`);
    }
  };

  const handleDelete = async (name) => {
    if (!confirm(`Delete project "${name}"? This cannot be undone.`)) return;
    await deleteProject(name);
    if (currentProject === name) setCurrentProject(null);
    await refreshProjects();
  };

  const handleOpen = (name) => setCurrentProject(name);
  const handleBack = () => { setCurrentProject(null); refreshProjects(); };

  if (currentProject) {
    return <Workspace projectName={currentProject} onBack={handleBack} />;
  }

  return (
    <div className="min-h-screen bg-[#0f1419]">
      <header className="border-b border-gray-800 px-6 py-4">
        <h1 className="text-2xl font-bold text-[#e0ddaa]">ZAO Video Editor</h1>
        <p className="text-sm text-gray-400 mt-1">Local video processing for conversation-based content</p>
      </header>
      <main className="max-w-4xl mx-auto p-6">
        {loading ? (
          <p className="text-gray-400">Loading...</p>
        ) : (
          <ProjectList
            projects={projects}
            onCreate={handleCreate}
            onOpen={handleOpen}
            onDelete={handleDelete}
          />
        )}
      </main>
    </div>
  );
}
