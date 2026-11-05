import { useState } from 'react';
import type { CSSProperties } from 'react';

const nodes = {
  entry: [37, 215],
  north: [112, 86],
  west: [116, 238],
  branch: [199, 120],
  relay: [226, 206],
  uplink: [352, 95],
  east: [411, 197],
  southeast: [334, 313],
  south: [190, 339],
  southwest: [80, 317],
} as const;

type Node = keyof typeof nodes;

const links: [Node, Node][] = [
  ['entry', 'north'],
  ['entry', 'west'],
  ['north', 'west'],
  ['north', 'branch'],
  ['west', 'relay'],
  ['west', 'southwest'],
  ['branch', 'relay'],
  ['branch', 'uplink'],
  ['relay', 'uplink'],
  ['relay', 'east'],
  ['relay', 'south'],
  ['relay', 'southeast'],
  ['uplink', 'east'],
  ['east', 'southeast'],
  ['south', 'southeast'],
  ['south', 'southwest'],
];
const route = ['entry', 'west', 'relay', 'branch', 'uplink'] as const;

function NetworkSubnet({ phase }: { phase: number }) {
  return (
    <g>
      <g className="inspection-links">
        {links.map(([from, to]) => (
          <line
            key={`${from}-${to}`}
            x1={nodes[from][0]}
            y1={nodes[from][1]}
            x2={nodes[to][0]}
            y2={nodes[to][1]}
          />
        ))}
      </g>
      <g className="inspection-nodes">
        {Object.entries(nodes).map(([name, [cx, cy]]) => (
          <circle key={name} cx={cx} cy={cy} r={name === 'relay' ? 6 : 3.5} />
        ))}
      </g>
      {route.slice(1).map((to, index) => {
        const from = route[index];
        const [x1, y1] = nodes[from];
        const [x2, y2] = nodes[to];
        const dx = x2 - x1;
        const dy = y2 - y1;
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        const delay = phase + index * 0.8;
        const style = {
          '--hop-delay': `${delay}s`,
          '--hop-length': `${Math.hypot(dx, dy)}px`,
        } as CSSProperties;
        return (
          <g key={to} style={style}>
            <line className="inspection-hop" x1={x1} y1={y1} x2={x2} y2={y2} />
            <g transform={`translate(${x1} ${y1}) rotate(${angle})`}>
              <circle className="inspection-packet" r="4" />
            </g>
            <circle className="inspection-ripple" cx={x2} cy={y2} r="8" />
          </g>
        );
      })}
    </g>
  );
}

export function InspectionBackdrop() {
  const [paused, setPaused] = useState(false);
  const action = paused ? 'Play background animation' : 'Pause background animation';

  return (
    <>
      <div className="inspection-backdrop" data-paused={paused} aria-hidden="true">
        <svg
          className="inspection-subnet-west"
          viewBox="0 0 460 400"
          preserveAspectRatio="xMinYMid meet"
          focusable="false"
        >
          <NetworkSubnet phase={-1.9} />
        </svg>
        <svg
          className="inspection-subnet-east"
          viewBox="0 0 460 400"
          preserveAspectRatio="xMaxYMid meet"
          focusable="false"
        >
          <g transform="rotate(180 230 200)">
            <NetworkSubnet phase={-6.4} />
          </g>
        </svg>
      </div>
      <button
        className="inspection-motion-toggle"
        type="button"
        aria-label={action}
        title={action}
        onClick={() => setPaused(!paused)}
      >
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d={paused ? 'M5 3.5 12 8 5 12.5Z' : 'M5 4h2v8H5zm4 0h2v8H9z'} />
        </svg>
      </button>
    </>
  );
}
