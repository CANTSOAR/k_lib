import React, { useState, useEffect, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';
import * as d3 from 'd3';
import 'katex/dist/katex.min.css';
import katex from 'katex';

// --- CONFIGURATION ---
const API_URL = "http://localhost:8000";

const COLORS = {
  bgLight: "#e8e0d4",
  bgDark: "#dcc9a8",
  accent: "#b2a68c",
  textMain: "#50483b",
  textDark: "#141215",
  cardBg: "#f7f3eb"
};

const EDGE_COLORS = {
  "CITES": "#141215",
  "SIMILAR_MODEL": "#a34905",
  "SIMILAR_METHODOLOGY": "#b2a68c",
  "SIMILAR_RESULTS": "#6b8e23",
  "SIMILAR_DATA_DESCRIPTION": "#4682b4",
  "OTHER": "#999999"
};

// Helper: Map edge type to readable label
const getEdgeLabel = (type) => {
  if (type.includes("MODEL")) return "Theory / Model";
  if (type.includes("METHOD")) return "Methodology";
  if (type.includes("RESULT")) return "Results";
  if (type.includes("DATA")) return "Data";
  if (type.includes("CITE")) return "Citation";
  return type.replace("SIMILAR_", "");
};

// Helper: Map edge type to section code (to find source text)
const EDGE_TO_CODE = {
  "SIMILAR_MODEL": "EQ",
  "SIMILAR_METHODOLOGY": "ME",
  "SIMILAR_RESULTS": "RE",
  "SIMILAR_DATA_DESCRIPTION": "DA",
  "SIMILAR_ABSTRACT": "AB",
  "SIMILAR_INTRODUCTION": "IN",
  "SIMILAR_CONCLUSION": "CO",
  "SIMILAR_LITERATURE_REVIEW": "LR",
  "SIMILAR_LIMITATIONS": "LI",
  "SIMILAR_FUTURE_WORK": "FU",
  "SIMILAR_APPENDIX": "AP",
  "SIMILAR_ACKNOWLEDGEMENTS": "AK",
  "SIMILAR_REFERENCES": "REF"
};

// Helper: Render LaTeX math in content
// NEW OPTIMIZED LatexContent to prevent crashes
const LatexContent = React.memo(({ content, isFullArticle = false }) => {
  if (!content) return null;

  // 1. PRE-PROCESSING: Clean up LaTeX commands to prepare for KaTeX
  const cleanLatex = (text) => {
    // TRUNCATION: Increase limit signifcantly for full article mode
    const limit = isFullArticle ? 500000 : 2000;
    let processed = text.length > limit ? text.substring(0, limit) + "... [Truncated]" : text;

    // === AGGRESSIVE CLEANUP ===
    processed = processed
      // Remove LaTeX comments (% to end of line)
      .replace(/%[^\n]*/g, '')
      // Remove fragmentary macro outputs like #1}}, #1}
      .replace(/#\d+\}+/g, '')
      .replace(/#\d+/g, '')
      // Remove lines that are just braces/brackets or junk
      .replace(/^\s*[\{\}\[\]]+\s*$/gm, '')
      .replace(/^\s*--\s*\w+\s*$/gm, '') // Author junk
      .replace(/\{ -- \w+ \d+mm\}/g, '')

      // Remove dimension specifications
      .replace(/\{[\d\w\s+\-\.]*pt[\d\w\s+\-\.]*\}/g, '')
      .replace(/\d+pt\b/g, '')

      // --- Structural cleanup ---
      .replace(/\\begin\{document\}|\\end\{document\}|\\maketitle|\\tableofcontents/g, '')
      .replace(/\\section\{([^}]*)\}/g, '\n\n**$1**\n\n')
      .replace(/\\subsection\{([^}]*)\}/g, '\n**$1**\n')
      .replace(/\\begin\{abstract\}/g, '')
      .replace(/\\end\{abstract\}/g, '')

      // --- Remove basic formatting/preamble that KaTeX doesn't like ---
      .replace(/\\(vspace|hspace|vskip|kern)\{[^}]*\}/g, '')
      .replace(/\\(noindent|bigskip|medskip|smallskip|newpage|clearpage|vfill|pagebreak)/g, '')
      .replace(/\\(thispagestyle|pagestyle|Authands|affiliation|email)\{[^}]*\}/g, '')
      .replace(/\\(titlespacing|singlespacing|doublespacing|centering)/g, '')

      // --- Handle citations and references visually ---
      .replace(/\\cite\{([^}]*)\}/g, (match, p1) => `[${p1}]`)
      .replace(/\\citep\{([^}]*)\}/g, (match, p1) => `[${p1}]`)
      .replace(/\\citet\{([^}]*)\}/g, (match, p1) => `${p1}`)
      .replace(/\\ref\{([^}]*)\}/g, (match, p1) => `[Ref: ${p1}]`)
      .replace(/\\label\{[^}]*\}/g, '')
      .replace(/\\footnote\{[^}]*\}/g, '')

      // --- MATH FIXES (Double Superscripts) ---
      .replace(/(\^\{[^}]+\})\s*(\^\{[^}]+\})/g, (match, p1, p2) => `^{${p1.slice(2, -1)}, ${p2.slice(2, -1)}}`)
      .replace(/(_\{[^}]+\})\s*(_\{[^}]+\})/g, (match, p1, p2) => `_{${p1.slice(2, -1)}, ${p2.slice(2, -1)}}`)
      // Also catch weird double superscripts with spaces or different bracing
      .replace(/\^([^{])\^([^{])/g, '^{$1, $2}')

      // --- Normalize Math Environments to $$ ... $$ for easier parsing ---
      .replace(/\\begin\{equation\*?\}([\s\S]*?)\\end\{equation\*?\}/g, '$$$1$$')
      .replace(/\\begin\{align\*?\}([\s\S]*?)\\end\{align\*?\}/g, '$$\\begin{aligned}$1\\end{aligned}$$')
      .replace(/\\begin\{gather\*?\}([\s\S]*?)\\end\{gather\*?\}/g, '$$\\begin{gathered}$1\\end{gathered}$$')
      .replace(/\\begin\{eqnarray\*?\}([\s\S]*?)\\end\{eqnarray\*?\}/g, '$$$1$$')
      .replace(/\\\[([\s\S]*?)\\\]/g, '$$$1$$')
      .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$'); // Convert \( ... \) to $ ... $

    // --- Text Formatting (Basic) ---
    // Convert LaTeX bold/italic to simpler markers (or just strip commands)
    processed = processed
      .replace(/\\textbf\{([^}]*)\}/g, '$1')
      .replace(/\\textit\{([^}]*)\}/g, '$1')
      .replace(/\\emph\{([^}]*)\}/g, '$1')
      .replace(/\\underline\{([^}]*)\}/g, '$1')
      .replace(/\\%|\\&|\\\$|\\#|\\_/g, (match) => match.slice(1)) // Unescape special chars in text mode
      .replace(/~/g, ' ')
      .trim();

    return processed;
  };

  // 2. PARSING: Split string by Math Delimiters
  const parseLatex = (text) => {
    // Regex explanation:
    // 1. ($$[\s\S]*?$$) -> Matches display math (greedy)
    // 2. ((?<!\\)\$(?!$)(?:\\.|[^\$])+(?<!\\)\$) -> Matches inline math $...$ 
    const regex = /(\$\$[\s\S]*?\$\$|(?<!\\)\$(?!$)(?:\\.|[^\$])+(?<!\\)\$)/g;

    // Split returns array: [text, math, text, math...]
    const parts = text.split(regex);

    // SAFETY PRE-CHECK
    const maxPartsCheck = isFullArticle ? 20000 : 1000;
    if (parts.length > maxPartsCheck) {
      return [<span key="fail" style={{ color: 'red' }}>Content too complex to render (Parts: {parts.length}).</span>];
    }

    const result = [];
    let loopCount = 0;
    const MAX_PARTS = isFullArticle ? 10000 : 500; // SAFETY: Max iterations

    for (let i = 0; i < parts.length; i++) {
      if (loopCount++ > MAX_PARTS) {
        result.push(<span key={i} style={{ color: 'orange' }}>... [Content Truncated Safety] ...</span>);
        break;
      }

      const part = parts[i];
      if (!part) continue;

      // Check if this part is Display Math ($$ ... $$)
      if (part.startsWith('$$') && part.endsWith('$$')) {
        const mathContent = part.slice(2, -2);
        try {
          const html = katex.renderToString(mathContent, {
            displayMode: true,
            throwOnError: false,
            trust: true,
            strict: false
          });
          result.push(
            <div
              key={i}
              style={{
                margin: '10px 0',
                overflowX: 'hidden',
                textAlign: 'center'
              }}
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        } catch (e) {
          result.push(<div key={i} style={{ color: '#999', fontSize: '0.8em' }}>[Math Error: {mathContent.substring(0, 30)}...]</div>);
        }
      }

      // Check if this part is Inline Math ($ ... $)
      else if (part.startsWith('$') && part.endsWith('$')) {
        const mathContent = part.slice(1, -1);
        try {
          const html = katex.renderToString(mathContent, {
            displayMode: false,
            throwOnError: false,
            trust: true,
            strict: false
          });
          result.push(
            <span
              key={i}
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        } catch (e) {
          result.push(<span key={i} style={{ color: '#999' }}>[{mathContent}]</span>);
        }
      }

      // Otherwise, it's regular text
      else {
        result.push(
          <span key={i}>
            {part.split('\n').map((line, j) => (
              <React.Fragment key={j}>
                {line}
                {j < part.split('\n').length - 1 && <br />}
              </React.Fragment>
            ))}
          </span>
        );
      }
    }
    return result;
  };

  try {
    const cleanText = cleanLatex(content);
    return (
      <div style={{
        whiteSpace: 'pre-wrap',
        lineHeight: '1.6',
        fontSize: '0.95rem',
        color: '#333'
      }}>
        {parseLatex(cleanText)}
      </div>
    );
  } catch (err) {
    console.error("Critical rendering error:", err);
    return <div style={{ color: 'red' }}>Error rendering content.</div>;
  }
});

function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [selectedPaper, setSelectedPaper] = useState(null);
  const [paperDetails, setPaperDetails] = useState(null);
  const [fullArticle, setFullArticle] = useState(null); // Full LaTeX content
  const [connections, setConnections] = useState([]);
  const [activeTab, setActiveTab] = useState("read"); // 'read' or 'connect'
  const [visibleEdgeTypes, setVisibleEdgeTypes] = useState(() =>
    Object.fromEntries(Object.keys(EDGE_COLORS).map(k => [k, true]))
  );
  const graphRef = useRef();

  // Toggle edge type visibility
  const toggleEdgeType = (edgeType) => {
    setVisibleEdgeTypes(prev => ({
      ...prev,
      [edgeType]: !prev[edgeType]
    }));
  };

  // Filter graph data based on visible edge types
  const filteredGraphData = {
    nodes: graphData.nodes,
    links: graphData.links.filter(link => {
      const type = link.type.toUpperCase();
      // Map link type to EDGE_COLORS key
      if (type.includes("MODEL") && !visibleEdgeTypes["SIMILAR_MODEL"]) return false;
      if (type.includes("METHOD") && !visibleEdgeTypes["SIMILAR_METHODOLOGY"]) return false;
      if (type.includes("RESULT") && !visibleEdgeTypes["SIMILAR_RESULTS"]) return false;
      if (type.includes("DATA") && !visibleEdgeTypes["SIMILAR_DATA_DESCRIPTION"]) return false;
      if (type.includes("CITE") && !visibleEdgeTypes["CITES"]) return false;
      // Check for OTHER - anything that doesn't match above categories
      const isOther = !type.includes("MODEL") && !type.includes("METHOD") &&
        !type.includes("RESULT") && !type.includes("DATA") && !type.includes("CITE");
      if (isOther && !visibleEdgeTypes["OTHER"]) return false;
      return true;
    })
  };

  // 1. Fetch Graph
  useEffect(() => {
    axios.get(`${API_URL}/graph`)
      .then(res => setGraphData(res.data))
      .catch(err => console.error("Error fetching graph:", err));
  }, []);

  // 2. Handle Node Click
  const handleNodeClick = (node) => {
    // Zoom to node
    graphRef.current.centerAt(node.x, node.y, 1000);
    graphRef.current.zoom(5, 2000);

    setSelectedPaper(node);
    setActiveTab("read"); // Reset to read view
    setFullArticle(null); // Reset full article
    setPaperDetails(null); // Clear previous details

    // Fetch Full Paper Details
    axios.get(`${API_URL}/paper/${node.id}`)
      .then(res => setPaperDetails(res.data))
      .catch(err => console.error(err));

    // Fetch Connections Analysis
    axios.get(`${API_URL}/paper/${node.id}/connections`)
      .then(res => setConnections(res.data))
      .catch(err => console.error(err));
  };

  // Zoom control functions
  const handleZoomIn = () => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom();
      graphRef.current.zoom(currentZoom * 1.5, 300);
    }
  };

  const handleZoomOut = () => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom();
      graphRef.current.zoom(currentZoom / 1.5, 300);
    }
  };

  const handleZoomReset = () => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(400, 50);
    }
  };

  // Count visual connections for selected paper
  const getVisualConnectionCount = () => {
    if (!selectedPaper || !graphData.links) return 0;
    return graphData.links.filter(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
      const targetId = typeof link.target === 'object' ? link.target.id : link.target;
      return sourceId === selectedPaper.id || targetId === selectedPaper.id;
    }).length;
  };

  // Fetch full article source
  const fetchFullArticle = () => {
    if (!selectedPaper) return;
    axios.get(`${API_URL}/paper/${selectedPaper.id}/full_source`)
      .then(res => setFullArticle(res.data.content))
      .catch(err => console.error("Error fetching full source:", err));
  };

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', fontFamily: 'Courier New', color: COLORS.textMain, overflow: 'hidden' }}>

      {/* === LEFT PANEL: GRAPH === */}
      <div style={{ width: '50%', minWidth: '400px', backgroundColor: COLORS.bgLight, position: 'relative', borderRight: `4px solid ${COLORS.accent}`, overflow: 'hidden' }}>
        <ForceGraph2D
          ref={graphRef}
          graphData={filteredGraphData}
          width={window.innerWidth / 2}
          height={window.innerHeight}
          nodeLabel="name"
          nodeColor={() => COLORS.bgDark}
          nodeRelSize={6}
          linkColor={link => {
            const type = link.type.toUpperCase();
            if (type.includes("MODEL")) return EDGE_COLORS.SIMILAR_MODEL;
            if (type.includes("METHOD")) return EDGE_COLORS.SIMILAR_METHODOLOGY;
            if (type.includes("RESULT")) return EDGE_COLORS.SIMILAR_RESULTS;
            if (type.includes("CITE")) return EDGE_COLORS.CITES;
            return EDGE_COLORS.OTHER;
          }}
          linkWidth={link => link.weight * 3 + 1}
          onNodeClick={handleNodeClick}
          backgroundColor={COLORS.bgLight}
          d3Force="center"
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          onEngineStop={() => { }}
          cooldownTicks={100}
          onEngineTick={() => {
            // Apply gravity force to keep nodes centered
            if (graphRef.current) {
              const fg = graphRef.current;
              fg.d3Force('charge')?.strength(-100);
              fg.d3Force('center', d3.forceCenter(0, 0));
              fg.d3Force('x', d3.forceX(0).strength(0.05));
              fg.d3Force('y', d3.forceY(0).strength(0.05));
            }
          }}
        />
        {/* Graph Legend Overlay - Clickable Toggles */}
        <div style={{
          position: 'absolute', bottom: 20, left: 20,
          padding: '10px', background: COLORS.bgDark,
          border: `1px solid ${COLORS.accent}`, borderRadius: '5px', fontSize: '0.8em'
        }}>
          <div style={{ marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em', opacity: 0.7 }}>Toggle Edge Types</div>
          {Object.entries(EDGE_COLORS).map(([key, color]) => (
            <div
              key={key}
              onClick={() => toggleEdgeType(key)}
              style={{
                display: 'flex', alignItems: 'center', marginBottom: 4,
                cursor: 'pointer', opacity: visibleEdgeTypes[key] ? 1 : 0.4,
                transition: 'opacity 0.2s'
              }}
            >
              <span style={{
                width: 10, height: 10,
                background: visibleEdgeTypes[key] ? color : '#ccc',
                marginRight: 8, display: 'inline-block',
                border: visibleEdgeTypes[key] ? 'none' : '1px solid #999'
              }}></span>
              <span style={{ textDecoration: visibleEdgeTypes[key] ? 'none' : 'line-through' }}>
                {getEdgeLabel(key)}
              </span>
            </div>
          ))}
        </div>

        {/* Zoom Controls Overlay */}
        <div style={{
          position: 'absolute', top: 20, left: 20,
          display: 'flex', flexDirection: 'column', gap: '5px'
        }}>
          <button
            onClick={handleZoomIn}
            style={{
              width: '30px', height: '30px', fontSize: '1.2em', fontWeight: 'bold',
              border: `2px solid ${COLORS.accent}`, borderRadius: '2px',
              background: COLORS.bgDark, cursor: 'pointer', color: COLORS.textDark,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, lineHeight: 1
            }}
          >
            +
          </button>
          <button
            onClick={handleZoomOut}
            style={{
              width: '30px', height: '30px', fontSize: '1.2em', fontWeight: 'bold',
              border: `2px solid ${COLORS.accent}`, borderRadius: '2px',
              background: COLORS.bgDark, cursor: 'pointer', color: COLORS.textDark,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, lineHeight: 1
            }}
          >
            -
          </button>
          <button
            onClick={handleZoomReset}
            style={{
              width: '30px', height: '30px', fontSize: '0.7em', fontWeight: 'bold',
              border: `2px solid ${COLORS.accent}`, borderRadius: '2px',
              background: COLORS.bgDark, cursor: 'pointer', color: COLORS.textDark,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, lineHeight: 1
            }}
          >
            FIT
          </button>
        </div>
      </div>

      {/* === RIGHT PANEL: READER & COMPARISON === */}
      <div style={{ width: '50%', minWidth: '400px', display: 'flex', flexDirection: 'column', backgroundColor: COLORS.cardBg, overflow: 'hidden' }}>

        {selectedPaper ? (
          <>
            {/* Header */}
            <div style={{ padding: '20px', background: COLORS.bgDark, borderBottom: `2px solid ${COLORS.accent}` }}>
              <h2 style={{ margin: 0, color: COLORS.textDark, fontSize: '1.2em' }}>{paperDetails?.title || selectedPaper.name}</h2>
              <div style={{ marginTop: '15px', display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => setActiveTab("read")}
                  style={{
                    padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: 'bold',
                    background: activeTab === 'read' ? COLORS.textMain : COLORS.bgLight,
                    color: activeTab === 'read' ? '#fff' : COLORS.textMain
                  }}
                >
                  📖 Read Paper
                </button>
                <button
                  onClick={() => setActiveTab("connect")}
                  style={{
                    padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: 'bold',
                    background: activeTab === 'connect' ? COLORS.textMain : COLORS.bgLight,
                    color: activeTab === 'connect' ? '#fff' : COLORS.textMain
                  }}
                >
                  Analyze Connections ({getVisualConnectionCount()})
                </button>
                {paperDetails?.arxiv_url && (
                  <a
                    href={paperDetails.arxiv_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: 'bold', marginLeft: 'auto',
                      background: COLORS.accent,
                      color: '#fff',
                      textDecoration: 'none',
                      borderRadius: '4px'
                    }}
                  >
                    View on arXiv
                  </a>
                )}
              </div>
            </div>

            {/* Content Area - different overflow for different tabs */}
            <div style={{
              flex: 1,
              overflow: activeTab === 'read' ? 'hidden' : 'auto',
              padding: activeTab === 'read' ? '0' : '20px'
            }}>

              {/* --- VIEW 1: PDF READER --- */}
              {activeTab === "read" && paperDetails && (
                <iframe
                  src={`${API_URL}/pdfs/${paperDetails.filename}/${paperDetails.filename}.pdf`}
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    backgroundColor: COLORS.cardBg
                  }}
                  title="PDF Viewer"
                />
              )}

              {/* --- VIEW 2: CONNECTION COMPARISON --- */}
              {activeTab === "connect" && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                  {connections.map((conn, idx) => {
                    // Find the MATCHING section in the SOURCE paper to display side-by-side
                    const sectionCode = EDGE_TO_CODE[conn.edge_type];
                    const sourceSection = paperDetails?.sections.find(s => s.section_code === sectionCode);
                    const borderColor = EDGE_COLORS[conn.edge_type] || COLORS.accent;

                    return (
                      <div key={idx} style={{
                        border: `1px solid ${borderColor}`,
                        background: '#fff',
                        borderRadius: '8px',
                        overflow: 'auto'
                      }}>
                        {/* Card Header */}
                        <div style={{
                          padding: '10px 15px',
                          background: `${borderColor}22`, // low opacity bg
                          borderBottom: `1px solid ${borderColor}`,
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          gap: '10px'
                        }}>
                          <span style={{ fontWeight: 'bold', color: COLORS.textDark, flex: 1 }}>
                            {conn.target_title}
                          </span>
                          <button
                            onClick={() => {
                              // Find the node and simulate a click
                              const targetNode = graphData.nodes.find(n => n.id === conn.target_id);
                              if (targetNode) {
                                handleNodeClick(targetNode);
                              }
                            }}
                            style={{
                              padding: '4px 10px',
                              fontSize: '0.8em',
                              border: `1px solid ${borderColor}`,
                              borderRadius: '4px',
                              background: '#fff',
                              color: borderColor,
                              cursor: 'pointer',
                              fontWeight: 'bold'
                            }}
                          >
                            Go To →
                          </button>
                          <span style={{
                            fontSize: '0.8em', padding: '2px 8px', borderRadius: '4px',
                            background: borderColor, color: '#fff'
                          }}>
                            {getEdgeLabel(conn.edge_type)} ({conn.similarity_score.toFixed(2)})
                          </span>
                        </div>

                        {/* Comparison View */}
                        <div style={{ display: 'flex', fontSize: '0.85em' }}>

                          {/* Left: Source Text */}
                          <div style={{ width: '50%', padding: '15px', borderRight: '1px solid #eee', boxSizing: 'border-box' }}>
                            <strong style={{ display: 'block', marginBottom: '8px', color: COLORS.accent }}>
                              THIS PAPER ({getEdgeLabel(conn.edge_type)})
                            </strong>
                            <div style={{ maxHeight: '200px', overflowX: 'hidden', overflowY: 'auto', fontWeight: 600 }}>
                              {sourceSection ? <LatexContent content={sourceSection.content} /> : "Section text not available."}
                            </div>
                          </div>

                          {/* Right: Target Text */}
                          <div style={{ width: '50%', padding: '15px', background: '#fafafa', boxSizing: 'border-box' }}>
                            <strong style={{ display: 'block', marginBottom: '8px', color: borderColor }}>
                              CONNECTED PAPER
                            </strong>
                            <div style={{ maxHeight: '200px', overflowX: 'hidden', overflowY: 'auto', fontWeight: 600 }}>
                              {conn.matching_section_content ? <LatexContent content={conn.matching_section_content} /> :
                                (conn.edge_type === "CITES" ? "Explicit Citation found in bibliography." : "Text content not indexed.")}
                            </div>
                          </div>

                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', opacity: 0.5 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '3em', marginBottom: '10px' }}>👈</div>
              Select a paper node to read and analyze.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;