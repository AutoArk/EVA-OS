import CustomHeader from "@/components/custom-header";
import { toast, Toaster } from "@/components/sonner";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Text } from "@/components/ui/text";
import { Env } from "@/constants/env";
import { useApiKey } from "@/hooks/use-api-key";
import { usePermission } from "@/hooks/use-permission";
import { usePlatform } from "@/hooks/use-platform";
import { EvaClient, IRoomInfo } from "@/lib/eva-client";
import { cn } from "@/lib/utils";
import { ISimpleSolution } from "@/models/solution";
import { getSimpleSolution } from "@/services/solution";
import { AudioSession, LiveKitRoom } from "@livekit/react-native";
import {
  default as Geolocation,
  GeolocationResponse,
} from "@react-native-community/geolocation";
import { useKeepAwake } from "expo-keep-awake";
import { useNetworkState } from "expo-network";
import gcoord from "gcoord";
import { Loader2, Phone } from "lucide-react-native";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Linking, PermissionsAndroid, Platform, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaView } from "react-native-safe-area-context";
import RoomView from "./room-view";
import SolutionInfo from "./solution-info";

const convertToGcj02 = (
  location: GeolocationResponse
): GeolocationResponse => {
  const wgs84Coords: [number, number] = [
    location.coords.longitude,
    location.coords.latitude,
  ];
  const gcj02Coords = gcoord.transform(
    wgs84Coords,
    gcoord.WGS84,
    gcoord.GCJ02
  ) as [number, number];

  const convertedLocation = {
    ...location,
    coords: {
      ...location.coords,
      longitude: gcj02Coords[0],
      latitude: gcj02Coords[1],
    },
  };
  return convertedLocation;
};

export default function ChatScreen() {
  const [headerBottom, setHeaderBottom] = useState(0);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [token, setToken] = useState("");
  const { apiKey } = useApiKey();
  const [evaClient, setEvaClient] = useState<EvaClient | null>(null);
  const [solutionInfo, setSolutionInfo] = useState<ISimpleSolution | null>(
    null
  );
  const {
    isMicrophoneGranted,
    isMicrophoneDenied,
    requestMicrophonePermission,
  } = usePermission();
  const networkState = useNetworkState();
  const { isIOS } = usePlatform();

  useKeepAwake();

  useEffect(() => {
    if (apiKey) {
      setEvaClient(new EvaClient(Env.baseUrl, Env.wssUrl, apiKey));
    }
  }, [apiKey]);

  useEffect(() => {
    getSimpleSolution(apiKey).then((data) => {
      if (data) {
        setSolutionInfo(data);
      }
    });
  }, [apiKey]);

  useEffect(() => {
    let start = async () => {
      await AudioSession.startAudioSession();
    };

    start();
    return () => {
      AudioSession.stopAudioSession();
    };
  }, []);

  useEffect(() => {
    let toastId = null;
    if (isMicrophoneDenied && !isConnected) {
      toastId = toast(
        "您已拒绝麦克风权限，如需使用音频功能，请在系统设置中打开权限",
        {
          action: {
            label: "去设置",
            onClick: () => {
              Linking.openSettings();
            },
          },
          variant: "none",
          duration: Infinity,
        }
      );
    }
    return () => {
      toastId && toast.dismiss(toastId);
    };
  }, [isMicrophoneDenied, isConnected]);

  const buttonText = useMemo(() => {
    if (isConnecting) {
      return "正在连接";
    }
    return "拨打电话";
  }, [isConnecting]);

  const fetchAddress = useCallback(async () => {
    try {
      if (Platform.OS === "android") {
        await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
        );
      }

      return await new Promise<GeolocationResponse | null>((resolve) => {
        Geolocation.getCurrentPosition(
          (location) => {
            const convertedLocation = convertToGcj02(location);
            resolve(convertedLocation);
          },
          (error) => {
            console.log("获取定位出错:", error);
            resolve(null);
          },
          { enableHighAccuracy: true, timeout: 30000, maximumAge: 0 }
        );
      });
    } catch (error) {
      console.log("error:", error);
      return null;
    }
  }, []);

  const onConnect = useCallback(async () => {
    if (!isMicrophoneGranted) {
      const isGranted = await requestMicrophonePermission();
      if (!isGranted) return;
    }
    if (!networkState.isInternetReachable) {
      toast.error("网络异常连接失败，建议切换网络重试", {});
      return;
    }

    setIsConnecting(true);
    const getRoomParams: IRoomInfo = {};

    try {
      const needLocation = solutionInfo?.capabilities?.includes('geoinfo');
      if (needLocation) {
        const location = await fetchAddress();
        if (location) {
          getRoomParams.geo_info = {
            longitude: location.coords.longitude,
            latitude: location.coords.latitude,
          };
        }
      }
    } catch (error) {
      console.error("获取solution详情失败：", error);
      setIsConnecting(false);
      return;
    }

    evaClient
      ?.getRoom(getRoomParams)
      .then((res) => {
        setToken(res.roomToken);
        setIsConnected(true);
        toast.success("连接成功");
      })
      .catch((err) => {
        toast.error(err.message || "网络异常连接失败，建议切换网络重试", {});
      })
      .finally(() => {
        setIsConnecting(false);
      });
  }, [
    isMicrophoneGranted,
    networkState,
    evaClient,
    requestMicrophonePermission,
    solutionInfo,
    fetchAddress,
  ]);

  const onHeaderLayout = (num: number) => {
    setHeaderBottom(num);
  };

  const onConnectError = (error: Error) => {
    disconnect();
  };

  const disconnect = useCallback(() => {
    setIsConnected(false);
    setToken("");
  }, []);

  return (
    <SafeAreaView
      className={Platform.select({
        ios: "flex-1 bg-background pb-3",
        android: "flex-1 bg-background pb-12",
      })}
    >
      <GestureHandlerRootView>
        <CustomHeader
          title={solutionInfo?.name || ""}
          showBackButton={!isConnected}
          onLayout={onHeaderLayout}
        />
        <Toaster
          position="top-center"
          duration={1500}
          visibleToasts={1}
          toastOptions={{
            style: {
              top: isIOS ? headerBottom : 24,
              zIndex: 1000,
            },
          }}
        />
        <View
          className={cn("flex-1 flex-col items-center justify-around px-6")}
        >
          {isConnected ? (
            <LiveKitRoom
              serverUrl={evaClient?.wssUrl}
              token={token}
              connect={true}
              audio={true}
              video={false}
              onError={onConnectError}
            >
              <RoomView disconnect={disconnect} solutionInfo={solutionInfo} />
            </LiveKitRoom>
          ) : (
            solutionInfo && (
              <>
                <SolutionInfo
                  detail={solutionInfo?.description || ""}
                  avatar={solutionInfo?.metadata.iconBackground || ""}
                  icon={solutionInfo?.metadata.icon || ""}
                />
                <Button
                  className="w-full h-11"
                  onPress={onConnect}
                  disabled={isConnecting || isMicrophoneDenied}
                >
                  {isConnecting ? (
                    <View className="pointer-events-none animate-spin">
                      <Icon as={Loader2} className="text-primary-foreground" />
                    </View>
                  ) : (
                    <Icon
                      as={Phone}
                      className="text-primary-foreground size-4 mr-2"
                    />
                  )}
                  <Text>{buttonText}</Text>
                </Button>
              </>
            )
          )}
        </View>
      </GestureHandlerRootView>
    </SafeAreaView>
  );
}
