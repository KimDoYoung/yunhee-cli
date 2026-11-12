import React from 'react';
import { payApi } from '@/api/pay';

export const Pay34_Tab_WorkTimeConfig: React.FC = () => {
  const retrieve = () => payApi.searchWorkTimes();
  const save = () => payApi.saveWorkTimes([]);
  const remove = () => payApi.deleteWorkTimes([]);
  return <div>Pay34</div>;
};
