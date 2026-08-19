"use client";

import React from 'react';
import {
  Activity,
  GitBranch,
  ShieldCheck,
  BarChart3,
  Settings as SettingsIcon,
} from 'lucide-react';

export type MobileTab = 'overview' | 'dag' | 'evidence' | 'analytics' | 'settings';

interface MobileBottomNavProps {
  activeTab: string;
  onSelectTab: (tab: string) => void;
  onOpenSettings?: () => void;
}

const MOBILE_TABS: { id: MobileTab; label: string; icon: React.ElementType; mappedTab?: string }[] = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'dag', label: 'DAG', icon: GitBranch },
  { id: 'evidence', label: 'Evidence', icon: ShieldCheck },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'settings', label: 'More', icon: SettingsIcon },
];

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  onSelectTab,
  onOpenSettings,
}) => {
  return (
    <nav className="mobile-bottom-nav lg:hidden" aria-label="Mobile navigation">
      {MOBILE_TABS.map(tab => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id || activeTab === tab.mappedTab;

        return (
          <button
            key={tab.id}
            className={`mobile-nav-item ${isActive ? 'active' : ''}`}
            onClick={() => {
              if (tab.id === 'settings' && onOpenSettings) {
                onOpenSettings();
              } else {
                onSelectTab(tab.id);
              }
            }}
            aria-label={tab.label}
            aria-current={isActive ? 'page' : undefined}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
