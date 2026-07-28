import "./Dashboard.css";

function Dashboard() {

  // Mock data for now
  const stats = [
    { title: "Total Questions", value: 1245 },
    { title: "Active Users", value: 238 },
    { title: "Positive Feedback", value: "92%" },
    { title: "Avg Session Length", value: "8 min" }
  ];

  return (
    <div className="dashboard-container">

      <h1 className="dashboard-title">
        Admin Analytics Dashboard
      </h1>

      <div className="stats-grid">
        {stats.map((stat, index) => (
          <div className="stat-card" key={index}>
            <h3>{stat.title}</h3>
            <p>{stat.value}</p>
          </div>
        ))}
      </div>
        
      <div className="chart-section">
        <h2>Frequently Asked Topics</h2>

        <div className="topic-row">
          <span>Limits</span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: "90%" }}></div>
          </div>
        </div>

        <div className="topic-row">
          <span>Integration</span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: "75%" }}></div>
          </div>
        </div>

        <div className="topic-row">
          <span>Derivatives</span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: "60%" }}></div>
          </div>
        </div>

        <div className="topic-row">
          <span>Lagrange Multipliers</span>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: "45%" }}></div>
          </div>
        </div>

      </div>

    </div>
  );
}

export default Dashboard;