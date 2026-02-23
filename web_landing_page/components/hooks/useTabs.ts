import { useState } from 'react';

const useTabs = (init: number = 0): [number, (index: number) => void] => {
  const [activeTab, setActiveTab] = useState<number>(init);

  const handleTabClick = (index: number) => {
    setActiveTab(index);
  };

  return [activeTab, handleTabClick];
};

export default useTabs;