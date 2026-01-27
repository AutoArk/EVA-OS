import axios from 'axios';

export interface IRoom {
  roomId: string;
  roomToken: string;
}

export interface IRoomInfo {
  geo_info?: {
    latitude?: number;
    longitude?: number;
  };
}

export class EvaClient {
  constructor(
    public baseUrl: string,
    public wssUrl: string,
    public apiKey: string
  ) {}

  async getRoom(data: IRoomInfo): Promise<IRoom> {
    const response = await axios.post(`${this.baseUrl}/api/solution/chat-room`, data, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
    }).catch((error) => {
      throw new Error(error.response.data.message);
    });
    return response.data.data;
  }
}