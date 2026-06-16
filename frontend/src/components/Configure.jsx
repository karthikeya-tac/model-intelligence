import { useState } from 'react';
import Catalog from './Catalog';
import Intents from './Intents';
import ProvidersPanel from './ProvidersPanel';
import Compare from './Compare';
import ContextPanel from './ContextPanel';
import Activity from './Activity';

const TABS = [
  ['catalog', 'Model Catalog'],
  ['intents', 'Intent Map'],
  ['providers', 'Providers'],
  ['context', 'Context'],
  ['compare', 'Compare'],
  ['activity', 'Activity'],
];

export default function Configure() {
  const [tab, setTab] = useState('catalog');
  return (
    <div>
      <div className="nx-subnav">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {tab === 'catalog' && <Catalog />}
      {tab === 'intents' && <Intents />}
      {tab === 'providers' && <ProvidersPanel />}
      {tab === 'context' && <ContextPanel />}
      {tab === 'compare' && <Compare />}
      {tab === 'activity' && <Activity />}
    </div>
  );
}
