import {
  Activity,
  ArrowUpRight,
  Atom,
  Blocks,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cpu,
  Database,
  FileCode2,
  FileSearch,
  FolderGit2,
  Gauge,
  LayoutPanelLeft,
  type LucideIcon,
  Layers3,
  Orbit,
  ScanSearch,
  ScrollText,
  Settings2,
  Sparkles,
  Terminal,
  Workflow,
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

interface Metric {
  label: string;
  value: string;
  detail: string;
  tone: 'accent' | 'success' | 'neutral';
  icon: LucideIcon;
}

interface Stage {
  name: string;
  icon: LucideIcon;
}

interface LearningCard {
  id: string;
  projectName: string;
  source: string;
  status: 'learning' | 'completed' | 'queued';
  currentStageIndex: number;
  progress: number;
  accuracy: string;
  partitions: string;
  note: string;
}

interface TerminalEntry {
  level: 'info' | 'success' | 'warn';
  source: string;
  time: string;
  message: string;
}

interface PartitionInsight {
  title: string;
  description: string;
  outputs: string[];
}

const navItems: NavItem[] = [
  { id: 'overview', label: '总览', description: '项目态势与编排状态', icon: LayoutPanelLeft },
  { id: 'learn', label: '学习端', description: '阶段推进与知识提炼', icon: BrainCircuit },
  { id: 'signals', label: '信号', description: '分区摘要与执行指标', icon: Activity },
  { id: 'logs', label: '日志', description: '终端输出与实时事件', icon: Terminal },
];

const learningStages: Stage[] = [
  { name: '文件提取', icon: FileSearch },
  { name: '函数集语法语义分析', icon: FileCode2 },
  { name: '知识库构造', icon: Database },
  { name: '代码分区强化', icon: Layers3 },
  { name: '原子功能挖掘', icon: Atom },
  { name: '功能摘要生成', icon: ScrollText },
];

const metrics: Metric[] = [
  { label: '活跃学习流', value: '03', detail: '两个运行中，一个排队中', tone: 'accent', icon: Workflow },
  { label: '功能分区', value: '18', detail: '已固化为可复查摘要单元', tone: 'neutral', icon: Blocks },
  { label: '执行精度', value: '95.1%', detail: '最近四次任务平均一致性', tone: 'success', icon: Gauge },
  { label: '知识节点', value: '2.4k', detail: '继承 create_graph 图谱上下文', tone: 'neutral', icon: Orbit },
];

const learningCards: LearningCard[] = [
  {
    id: 'c1',
    projectName: 'create_graph / finance_cli',
    source: 'Workspace Session',
    status: 'learning',
    currentStageIndex: 3,
    progress: 72,
    accuracy: '94.6%',
    partitions: '6 / 8 完成强化',
    note: '当前聚焦执行流切片与功能层级摘要对齐。',
  },
  {
    id: 'c2',
    projectName: 'gitnexus baseline',
    source: 'Reference Mirror',
    status: 'completed',
    currentStageIndex: 5,
    progress: 100,
    accuracy: '96.3%',
    partitions: '12 个分区已归档',
    note: '图谱节点、右侧检索与工作台状态已归档到知识库。',
  },
  {
    id: 'c3',
    projectName: 'se_team dashboard shell',
    source: 'Mounted Frontend',
    status: 'queued',
    currentStageIndex: 0,
    progress: 0,
    accuracy: '--',
    partitions: '等待服务化验证',
    note: '预留同源接口挂接位，可后续替换为真实 API。',
  },
];

const partitionInsights: PartitionInsight[] = [
  {
    title: '程序管理与版本控制',
    description: '跟踪分支切换、frontier 选择与提交快照，适合承接 create_graph 的仓库切换与结果复现。',
    outputs: ['分支状态镜像', 'frontier 候选摘要', '切换行为日志'],
  },
  {
    title: '执行流与文本评估',
    description: '将函数链路、CFG / DFG 解读与文本匹配结果捆绑成统一学习单元，便于前端直读。',
    outputs: ['链路摘要', '容差评分', '上下文数字提取'],
  },
  {
    title: '技能进化循环',
    description: '对齐 run / feedback_history / no_improvement_count 的节奏，用于展示 Agent 学习闭环。',
    outputs: ['迭代次数', '候选优胜记录', '早停判定'],
  },
];

const terminalEntries: TerminalEntry[] = [
  {
    level: 'info',
    source: 'router',
    time: '09:41:12',
    message: 'Mounted frontend resolved at /se_team with dedicated asset prefix.',
  },
  {
    level: 'success',
    source: 'learn',
    time: '09:41:39',
    message: 'Partition summary batch #06 archived into workspace knowledge snapshot.',
  },
  {
    level: 'info',
    source: 'graph',
    time: '09:42:08',
    message: 'create_graph context synced: 2.4k nodes, 4.7k edges, 18 active function partitions.',
  },
  {
    level: 'warn',
    source: 'api',
    time: '09:42:31',
    message: 'Live API bridge still mocked; switch same-origin placeholders when contract stabilizes.',
  },
  {
    level: 'info',
    source: 'ui',
    time: '09:43:02',
    message: 'SE-team shell ready for future status polling via relative /api endpoints.',
  },
];

function App() {
  return (
    <div className="shell">
      <SideRail />
      <div className="shell-main">
        <TopBar />
        <main className="dashboard" id="overview">
          <section className="dashboard-main">
            <HeroPanel />
            <section className="metric-grid">
              {metrics.map((metric) => (
                <MetricCard key={metric.label} metric={metric} />
              ))}
            </section>
            <section className="section-block" id="learn">
              <SectionHeading
                eyebrow="Learning Orchestration"
                title="学习端编排视图"
                description="借鉴参考项目的 learn / model-card 结构，重组为 create_graph 的单页挂载控制台。"
              />
              <div className="learning-grid">
                {learningCards.map((card) => (
                  <LearningProgressCard key={card.id} card={card} />
                ))}
              </div>
            </section>
          </section>

          <aside className="dashboard-side">
            <section className="section-block spotlight-panel" id="signals">
              <SectionHeading
                eyebrow="Knowledge Signals"
                title="功能分区聚焦"
                description="围绕 learn / sidebar / terminal 的参考气质，强化知识分区、阶段状态与审阅入口。"
              />
              <div className="spotlight-stack">
                {partitionInsights.map((insight) => (
                  <PartitionCard key={insight.title} insight={insight} />
                ))}
              </div>
            </section>

            <section className="section-block" id="logs">
              <TerminalPanel entries={terminalEntries} />
            </section>
          </aside>
        </main>
      </div>
    </div>
  );
}

function SideRail() {
  return (
    <aside className="side-rail" aria-label="主导航侧边栏">
      <div className="rail-logo" aria-hidden="true">
        <Cpu className="rail-logo-icon" />
      </div>
      <nav className="rail-nav">
        {navItems.map((item, index) => {
          const Icon = item.icon;
          const active = index === 1;

          return (
            <a
              key={item.id}
              className={`rail-link${active ? ' is-active' : ''}`}
              href={`#${item.id}`}
              aria-label={`${item.label}：${item.description}`}
            >
              <Icon className="rail-link-icon" />
              <span className="rail-tooltip">
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </span>
            </a>
          );
        })}
      </nav>
      <button className="rail-link rail-link-button" type="button" aria-label="设置">
        <Settings2 className="rail-link-icon" />
      </button>
    </aside>
  );
}

function TopBar() {
  return (
    <header className="topbar">
      <div className="topbar-copy">
        <span className="eyebrow">Mounted Workspace</span>
        <div className="topbar-title-row">
          <h1>SE Team / create_graph</h1>
          <span className="status-pill status-pill-live">
            <span className="status-dot" />
            isolated frontend
          </span>
        </div>
        <p>独立部署于 <code>/se_team</code>，与现有 gitnexus 主页并行，不复用根级资源路由。</p>
      </div>
      <div className="topbar-actions">
        <div className="signal-chip">
          <FolderGit2 className="signal-chip-icon" />
          <span>D:\代码仓库生图\create_graph</span>
        </div>
        <button className="ghost-button" type="button">
          审阅挂载点
          <ArrowUpRight className="ghost-button-icon" />
        </button>
      </div>
    </header>
  );
}

function HeroPanel() {
  return (
    <section className="hero-panel">
      <div className="hero-copy">
        <span className="eyebrow">Industrial Learning Deck</span>
        <h2>面向 SE-team 的学习驾驶舱</h2>
        <p>
          参考侧边栏、学习卡片与日志终端的结构节奏，重绘为一个适配 create_graph 场景的暗色驾驶舱：
          一侧追踪知识提炼，一侧守住执行信号与输出日志。
        </p>
      </div>
      <div className="hero-badges">
        <Badge icon={BrainCircuit} label="learn-style pipeline" />
        <Badge icon={ScanSearch} label="same-origin API placeholders" />
        <Badge icon={Bot} label="single-page mounted shell" />
      </div>
      <div className="hero-highlight">
        <div className="highlight-card">
          <span className="highlight-label">当前阶段</span>
          <strong>代码分区及语义强化</strong>
          <span className="highlight-meta">正在将图谱节点与功能摘要重新锚定到统一知识切片。</span>
        </div>
        <div className="highlight-card highlight-card-terminal">
          <Terminal className="highlight-icon" />
          <div>
            <span className="highlight-label">输出姿态</span>
            <strong>终端与侧栏共振</strong>
            <span className="highlight-meta">保留参考项目的冷静工程感，但更贴近 create_graph 的分析上下文。</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({ metric }: { metric: Metric }) {
  const Icon = metric.icon;

  return (
    <article className={`metric-card metric-card-${metric.tone}`}>
      <div className="metric-card-header">
        <span>{metric.label}</span>
        <Icon className="metric-card-icon" />
      </div>
      <strong>{metric.value}</strong>
      <p>{metric.detail}</p>
    </article>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="section-heading">
      <span className="eyebrow">{eyebrow}</span>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

function LearningProgressCard({ card }: { card: LearningCard }) {
  const statusMeta = {
    learning: { label: '学习中', icon: Sparkles },
    completed: { label: '已完成', icon: CheckCircle2 },
    queued: { label: '排队中', icon: Clock3 },
  } as const;

  const status = statusMeta[card.status];
  const StatusIcon = status.icon;

  return (
    <article className={`learning-card status-${card.status}`}>
      <div className="learning-card-header">
        <div className="learning-card-title-group">
          <div className="learning-card-logo">
            <FolderGit2 className="learning-card-logo-icon" />
          </div>
          <div>
            <h4>{card.projectName}</h4>
            <p>{card.source}</p>
          </div>
        </div>
        <span className={`status-pill status-pill-${card.status}`}>
          <StatusIcon className="status-pill-icon" />
          {status.label}
        </span>
      </div>

      <div className="learning-card-stats">
        <StatTile label="准确率" value={card.accuracy} />
        <StatTile label="分区状态" value={card.partitions} />
      </div>

      <div className="stage-list">
        {learningStages.map((stage, index) => {
          const StageIcon = stage.icon;
          const isComplete = index < card.currentStageIndex || card.status === 'completed';
          const isCurrent = index === card.currentStageIndex && card.status === 'learning';
          const isQueued = card.status === 'queued';

          return (
            <div className="stage-row" key={stage.name}>
              <div className={`stage-icon-wrap${isComplete ? ' is-complete' : ''}${isCurrent ? ' is-current' : ''}${isQueued ? ' is-queued' : ''}`}>
                <StageIcon className="stage-icon" />
              </div>
              <div className="stage-content">
                <div className="stage-copy-row">
                  <span className={`stage-name${isComplete ? ' is-complete' : ''}${isCurrent ? ' is-current' : ''}${isQueued ? ' is-queued' : ''}`}>
                    {stage.name}
                  </span>
                  <span className="stage-value">
                    {isComplete ? '完成' : isCurrent ? `${card.progress}%` : '待命'}
                  </span>
                </div>
                <div className="progress-track" aria-hidden="true">
                  <span
                    className={`progress-fill${isComplete ? ' is-complete' : ''}${isCurrent ? ' is-current' : ''}`}
                    style={{ width: `${isComplete ? 100 : isCurrent ? card.progress : 8}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="learning-card-footer">
        <p>{card.note}</p>
        <button className="inline-link" type="button">
          查看知识摘要
          <ChevronRight className="inline-link-icon" />
        </button>
      </div>
    </article>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PartitionCard({ insight }: { insight: PartitionInsight }) {
  return (
    <article className="partition-card">
      <div className="partition-card-header">
        <span className="partition-card-dot" />
        <h4>{insight.title}</h4>
      </div>
      <p>{insight.description}</p>
      <ul className="partition-output-list">
        {insight.outputs.map((output) => (
          <li key={output}>{output}</li>
        ))}
      </ul>
    </article>
  );
}

function TerminalPanel({ entries }: { entries: TerminalEntry[] }) {
  return (
    <div className="terminal-panel">
      <div className="terminal-header">
        <div className="terminal-title-group">
          <Terminal className="terminal-title-icon" />
          <div>
            <strong>输出日志</strong>
            <span>{entries.length} 条实时事件</span>
          </div>
        </div>
        <span className="terminal-live-pill">
          <span className="status-dot" />
          streaming
        </span>
      </div>
      <div className="terminal-body">
        {entries.map((entry) => (
          <div className="terminal-row" key={`${entry.time}-${entry.source}-${entry.message}`}>
            <span className="terminal-time">{entry.time}</span>
            <span className={`terminal-level terminal-level-${entry.level}`}>{entry.level}</span>
            <span className="terminal-source">[{entry.source}]</span>
            <span className="terminal-message">{entry.message}</span>
          </div>
        ))}
        <div className="terminal-cursor">▍</div>
      </div>
    </div>
  );
}

function Badge({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <span className="badge-chip">
      <Icon className="badge-chip-icon" />
      {label}
    </span>
  );
}

export default App;
