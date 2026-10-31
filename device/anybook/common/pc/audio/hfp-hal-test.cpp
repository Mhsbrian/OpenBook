// SPDX-License-Identifier: Apache-2.0
// Disposable VM only. Uses a synthetic Bluetooth stack, never a radio or microphone.
#include <aidl/android/hardware/audio/core/IModule.h>
#include <aidl/android/hardware/bluetooth/audio/BnBluetoothAudioPort.h>
#include <aidl/android/hardware/bluetooth/audio/IBluetoothAudioProviderFactory.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <android-base/properties.h>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

namespace ac = aidl::android::hardware::audio::core;
namespace bt = aidl::android::hardware::bluetooth::audio;
namespace common = aidl::android::media::audio::common;
using ndk::ScopedAStatus;

static void require(bool ok, const char* what) {
    if (!ok) { fprintf(stderr, "FAIL %s\n", what); exit(1); }
}
static void check(const ScopedAStatus& status, const char* what) {
    if (!status.isOk()) {
        fprintf(stderr, "%s: %s\n", what, status.getDescription().c_str());
        exit(1);
    }
}
template <class T> static std::shared_ptr<T> service(const char* instance) {
    auto binder = ndk::SpAIBinder(AServiceManager_checkService(
            (std::string(T::descriptor) + "/" + instance).c_str()));
    require(binder.get() != nullptr, "service exists");
    auto result = T::fromBinder(binder);
    require(result != nullptr, "service interface");
    return result;
}
class Port : public bt::BnBluetoothAudioPort {
public:
    ScopedAStatus getPresentationPosition(bt::PresentationPosition* p) override {
        *p = {}; return ScopedAStatus::ok();
    }
    ScopedAStatus startStream(bool) override { return ScopedAStatus::ok(); }
    ScopedAStatus stopStream() override { return ScopedAStatus::ok(); }
    ScopedAStatus suspendStream() override { return ScopedAStatus::ok(); }
    ScopedAStatus updateSourceMetadata(
            const aidl::android::hardware::audio::common::SourceMetadata&) override {
        return ScopedAStatus::ok();
    }
    ScopedAStatus updateSinkMetadata(
            const aidl::android::hardware::audio::common::SinkMetadata&) override {
        return ScopedAStatus::ok();
    }
    ScopedAStatus setLatencyMode(bt::LatencyMode) override { return ScopedAStatus::ok(); }
    ScopedAStatus updateSinkLatency(int64_t) override { return ScopedAStatus::ok(); }
};

static common::AudioPortConfig configure(const std::shared_ptr<ac::IModule>& m,
                                         common::AudioPortConfig request) {
    common::AudioPortConfig result;
    bool applied = false;
    check(m->setAudioPortConfig(request, &result, &applied), "setAudioPortConfig");
    if (!applied) {
        request = result;
        check(m->setAudioPortConfig(request, &result, &applied), "apply suggested config");
    }
    require(applied && result.id != 0, "configuration applied");
    return result;
}

int main(int argc, char** argv) {
    require(argc == 2 && std::string(argv[1]) == "--disposable-vm", "explicit VM mode");
    require(android::base::GetProperty("ro.product.board", "") == "cutf" ||
            android::base::GetProperty("ro.boot.hardware", "") == "cutf", "Cuttlefish only");
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    ABinderProcess_startThreadPool();
    auto module = service<ac::IModule>("bluetooth");
    auto factory = service<bt::IBluetoothAudioProviderFactory>("default");
    std::shared_ptr<ac::IBluetooth> bluetooth;
    check(module->getBluetooth(&bluetooth), "getBluetooth");
    require(bluetooth != nullptr, "SCO control interface exposed");
    std::vector<common::AudioPort> ports;
    check(module->getAudioPorts(&ports), "getAudioPorts");
    std::vector<ac::AudioRoute> routes;
    check(module->getAudioRoutes(&routes), "getAudioRoutes");
    int cases = 0;
    for (int rate : {8000, 16000, 32000}) {
        for (bool input : {false, true}) {
            auto type = input ? bt::SessionType::HFP_SOFTWARE_DECODING_DATAPATH
                              : bt::SessionType::HFP_SOFTWARE_ENCODING_DATAPATH;
            std::shared_ptr<bt::IBluetoothAudioProvider> provider;
            check(factory->openProvider(type, &provider), "open HFP software provider");
            bt::PcmConfiguration pcm;
            pcm.sampleRateHz = rate;
            pcm.bitsPerSample = 16;
            pcm.channelMode = bt::ChannelMode::MONO;
            pcm.dataIntervalUs = 7500;
            auto host = ndk::SharedRefBase::make<Port>();
            aidl::android::hardware::common::fmq::MQDescriptor<
                    int8_t, aidl::android::hardware::common::fmq::SynchronizedReadWrite> queue;
            check(provider->startSession(host,
                      bt::AudioConfiguration::make<bt::AudioConfiguration::pcmConfig>(pcm),
                      {bt::LatencyMode::FREE}, &queue), "start HFP software session");
            require(queue.grantors.size() > 0, "HFP PCM queue");
            int connectedCount = 0;
            for (const auto& port : ports) {
                if (port.ext.getTag() != common::AudioPortExt::device) continue;
                const auto& dev = port.ext.get<common::AudioPortExt::device>();
                if (dev.device.type.connection != common::AudioDeviceDescription::CONNECTION_BT_SCO)
                    continue;
                if ((port.flags.getTag() == common::AudioIoFlags::input) != input) continue;
                auto request = port;
                request.ext.get<common::AudioPortExt::device>().device.address =
                    common::AudioDeviceAddress::make<common::AudioDeviceAddress::mac>(
                            std::vector<uint8_t>{2, 0, 0, 0, 0, 1});
                common::AudioPort connected;
                check(module->connectExternalDevice(request, &connected), "connect SCO device");
                require(connected.profiles.size() == 1, "SCO negotiated profile");
                require(connected.profiles[0].sampleRates == std::vector<int>{32000},
                        "HFP resampler exposes 32 kHz");
                common::AudioPortConfig deviceRequest;
                deviceRequest.portId = connected.id;
                auto deviceConfig = configure(module, deviceRequest);
                int mixId = 0;
                for (const auto& route : routes) {
                    if (!input && route.sinkPortId == port.id && route.sourcePortIds.size() == 1)
                        mixId = route.sourcePortIds[0];
                    if (input && route.sourcePortIds == std::vector<int>{port.id})
                        mixId = route.sinkPortId;
                }
                require(mixId != 0, "SCO mix route");
                common::AudioPortConfig mixRequest;
                mixRequest.portId = mixId;
                mixRequest.sampleRate = deviceConfig.sampleRate;
                mixRequest.channelMask = deviceConfig.channelMask;
                mixRequest.format = deviceConfig.format;
                mixRequest.ext = common::AudioPortExt::make<common::AudioPortExt::mix>(
                        common::AudioPortMixExt{.handle = 700 + cases});
                auto mixConfig = configure(module, mixRequest);
                ac::AudioPatch patch, result;
                patch.sourcePortConfigIds = {input ? deviceConfig.id : mixConfig.id};
                patch.sinkPortConfigIds = {input ? mixConfig.id : deviceConfig.id};
                check(module->setAudioPatch(patch, &result), "patch SCO route");
                std::shared_ptr<ac::IStreamCommon> stream;
                if (input) {
                    ac::IModule::OpenInputStreamArguments args;
                    args.portConfigId = mixConfig.id;
                    args.bufferSizeFrames = result.minimumStreamBufferSizeFrames;
                    ac::IModule::OpenInputStreamReturn out;
                    check(module->openInputStream(args, &out), "open SCO input");
                    check(out.stream->getStreamCommon(&stream), "input common");
                } else {
                    ac::IModule::OpenOutputStreamArguments args;
                    args.portConfigId = mixConfig.id;
                    args.bufferSizeFrames = result.minimumStreamBufferSizeFrames;
                    ac::IModule::OpenOutputStreamReturn out;
                    check(module->openOutputStream(args, &out), "open SCO output");
                    check(out.stream->getStreamCommon(&stream), "output common");
                }
                check(stream->close(), "close stream");
                check(module->resetAudioPatch(result.id), "reset patch");
                check(module->resetAudioPortConfig(mixConfig.id), "reset mix config");
                check(module->resetAudioPortConfig(deviceConfig.id), "reset device config");
                check(module->prepareToDisconnectExternalDevice(connected.id), "prepare disconnect");
                check(module->disconnectExternalDevice(connected.id), "disconnect SCO");
                ++connectedCount;
                ++cases;
            }
            require(connectedCount == (input ? 1 : 3), "all SCO device variants tested");
            check(provider->endSession(), "end HFP session");
            printf("PASS rate=%d direction=%s ports=%d\n", rate,
                    input ? "input" : "output", connectedCount);
        }
    }
    printf("PASS %d SCO route/stream cases; synthetic stack, no RF or call audio\n", cases);
    return 0;
}
