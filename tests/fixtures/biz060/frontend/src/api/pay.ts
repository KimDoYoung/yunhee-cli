import { apiClient } from './client';

export const payApi = {
  searchWorkTimes: async (): Promise<any[]> => {
    const res = await apiClient.get('v1/pay/work-times');
    return res.data;
  },
  saveWorkTimes: async (rows: any[]): Promise<any[]> => {
    const res = await apiClient.put('v1/pay/work-times', rows);
    return res.data;
  },
  deleteWorkTimes: async (ids: number[]): Promise<number> => {
    const res = await apiClient.delete('v1/pay/work-times', { data: ids });
    return res.data;
  },
};
