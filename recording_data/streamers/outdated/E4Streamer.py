from streamers import SensorStreamer
from visualizers import LinePlotVisualizer
from visualizers import HeatmapVisualizer

import socket
import numpy as np
import time
from collections import OrderedDict
import traceback
import pylsl

from utils.print_utils import *


################################################
################################################
# A template class for implementing a new sensor.
################################################
################################################
class E4Streamer(SensorStreamer):

    ########################
    ###### INITIALIZE ######
    ########################

    # Initialize the sensor streamer.
    # @param visualization_options Can be used to specify how data should be visualized.
    #   It should be a dictionary with the following keys:
    #     'visualize_streaming_data': Whether or not visualize any data during streaming.
    #     'update_period_s': How frequently to update the visualizations during streaming.
    #     'visualize_all_data_when_stopped': Whether to visualize a summary of data at the end of the experiment.
    #     'wait_while_visualization_windows_open': After the experiment finishes, whether to automatically close visualization windows or wait for the user to close them.
    #     'classes_to_visualize': [optional] A list of class names that should be visualized (others will be suppressed).  For example, ['TouchStreamer', 'MyoStreamer']
    #     'use_composite_video': Whether to combine visualizations from multiple streamers into a single tiled visualization.  If not, each streamer will create its own window.
    #     'composite_video_filepath': If using composite video, can specify a filepath to save it as a video.
    #     'composite_video_layout': If using composite video, can specify which streamers should be included and how to arrange them. See some of the launch files for examples.
    # @param log_player_options Can be used to replay data from an existing log instead of streaming real-time data.
    #   It should be a dictionary with the following keys:
    #     'log_dir': The directory with log data to replay (should directly contain the HDF5 file).
    #     'pause_to_replay_in_realtime': If reading from the logs is faster than real-time, can wait between reads to keep the replay in real time.
    #     'skip_timesteps_to_replay_in_realtime': If reading from the logs is slower than real-time, can skip timesteps as needed to remain in real time.
    #     'load_datasets_into_memory': Whether to load all data into memory before starting the replay, or whether to read from the HDF5 file each timestep.
    # @param print_status Whether or not to print messages with level 'status'
    # @param print_debug Whether or not to print messages with level 'debug'
    # @param log_history_filepath A filepath to save log messages if desired.
    def __init__(self,
                 log_player_options=None, visualization_options=None,
                 print_status=True, print_debug=False, log_history_filepath=None):
        SensorStreamer.__init__(self, streams_info=None,
                                visualization_options=visualization_options,
                                log_player_options=log_player_options,
                                print_status=print_status, print_debug=print_debug,
                                log_history_filepath=log_history_filepath)

        ## TODO: Add a tag here for your sensor that can be used in log messages.
        #        Try to keep it under 10 characters long.
        #        For example, 'myo' or 'scale'.
        self._log_source_tag = 'E4'

        ## TODO: Initialize any state that your sensor needs.
        # Initialize counts
        self._num_segments = None

        # Initialize state
        self._buffer = b''
        self._buffer_read_size = 4096
        self._socket = None
        self._E4_sample_index = None  # The current Moticon timestep being processed (each timestep will send multiple messages)
        self._E4_message_start_time_s = None  # When a Moticon message was first received
        self._E4_timestep_receive_time_s = None  # When the first Moticon message for a Moticon timestep was received
        self._device_id = 'D931CD'

        # SELECT DATA TO STREAM
        self._acc = True  # 3-axis acceleration
        self._bvp = True  # Blood Volume Pulse
        self._gsr = True  # Galvanic Skin Response (Electrodermal Activity)
        self._tmp = True  # Temperature

        # Specify the Moticon streaming configuration.
        self._E4_network_protocol = 'tcp'
        self._E4_network_ip = '127.0.0.6'
        self._E4_network_port = 3002

        ## TODO: Add devices and streams to organize data from your sensor.
        #        Data is organized as devices and then streams.
        #        For example, a Myo device may have streams for EMG and Acceleration.
        #        If desired, this could also be done in the connect() method instead.
        self.add_stream(device_name='ACC-empatica_e4',
                        stream_name='acc-values',
                        data_type='float32',
                        sample_size=[3],
                        # the size of data saved for each timestep; here, we expect a 2-element vector per timestep
                        sampling_rate_hz=32,  # the expected sampling rate for the stream
                        extra_data_info={},
                        # can add extra information beyond the data and the timestamp if needed (probably not needed, but see MyoStreamer for an example if desired)
                        # Notes can add metadata about the stream,
                        #  such as an overall description, data units, how to interpret the data, etc.
                        # The SensorStreamer.metadata_data_headings_key is special, and is used to
                        #  describe the headings for each entry in a timestep's data.
                        #  For example - if the data was saved in a spreadsheet with a row per timestep, what should the column headings be.
                        data_notes=OrderedDict([
                            ('Description', 'Acceleration data from empatica-e4.'
                             ),
                            ('Units', ''),
                            (SensorStreamer.metadata_data_headings_key,
                             ['acc_x', 'acc_y', 'acc_z']),
                        ]))
        self.add_stream(device_name='BVP-empatica_e4',
                        stream_name='bvp-values',
                        data_type='float32',
                        sample_size=[1],
                        # the size of data saved for each timestep; here, we expect a 2-element vector per timestep
                        sampling_rate_hz=64,  # the expected sampling rate for the stream
                        extra_data_info={},
                        # can add extra information beyond the data and the timestamp if needed (probably not needed, but see MyoStreamer for an example if desired)
                        # Notes can add metadata about the stream,
                        #  such as an overall description, data units, how to interpret the data, etc.
                        # The SensorStreamer.metadata_data_headings_key is special, and is used to
                        #  describe the headings for each entry in a timestep's data.
                        #  For example - if the data was saved in a spreadsheet with a row per timestep, what should the column headings be.
                        data_notes=OrderedDict([
                            ('Description', 'Pressure data from the left shoe.'
                             ),
                            ('Units', ''),
                            (SensorStreamer.metadata_data_headings_key,
                             ['bvp']),
                        ]))
        self.add_stream(device_name='GSR-empatica_e4',
                        stream_name='gsr-values',
                        data_type='float32',
                        sample_size=[1],
                        # the size of data saved for each timestep; here, we expect a 2-element vector per timestep
                        sampling_rate_hz=4,  # the expected sampling rate for the stream
                        extra_data_info={},
                        # can add extra information beyond the data and the timestamp if needed (probably not needed, but see MyoStreamer for an example if desired)
                        # Notes can add metadata about the stream,
                        #  such as an overall description, data units, how to interpret the data, etc.
                        # The SensorStreamer.metadata_data_headings_key is special, and is used to
                        #  describe the headings for each entry in a timestep's data.
                        #  For example - if the data was saved in a spreadsheet with a row per timestep, what should the column headings be.
                        data_notes=OrderedDict([
                            ('Description', 'Pressure data from the left shoe.'
                             ),
                            ('Units', ''),
                            (SensorStreamer.metadata_data_headings_key,
                             ['gsr']),
                        ]))
        self.add_stream(device_name='Tmp-empatica_e4',
                        stream_name='tmp-values',
                        data_type='float32',
                        sample_size=[1],
                        # the size of data saved for each timestep; here, we expect a 2-element vector per timestep
                        sampling_rate_hz=4,  # the expected sampling rate for the stream
                        extra_data_info={},
                        # can add extra information beyond the data and the timestamp if needed (probably not needed, but see MyoStreamer for an example if desired)
                        # Notes can add metadata about the stream,
                        #  such as an overall description, data units, how to interpret the data, etc.
                        # The SensorStreamer.metadata_data_headings_key is special, and is used to
                        #  describe the headings for each entry in a timestep's data.
                        #  For example - if the data was saved in a spreadsheet with a row per timestep, what should the column headings be.
                        data_notes=OrderedDict([
                            ('Description', 'Pressure data from the left shoe.'
                             ),
                            ('Units', ''),
                            (SensorStreamer.metadata_data_headings_key,
                             ['tmp']),
                        ]))

    #######################################
    # Connect to the sensor.
    # @param timeout_s How long to wait for the sensor to respond.
    def _connect(self, timeout_s=10):
        # Open a socket to the E4 network stream
        ## TODO: Add code for connecting to your sensor.
        #        Then return True or False to indicate whether connection was successful.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(3)

        print("Connecting to server")
        self._socket.connect((self._E4_network_ip, self._E4_network_port))
        print("Connected to server\n")

        print("Devices available:")
        self._socket.send("device_list\r\n".encode())
        response = self._socket.recv(self._buffer_read_size)

        print(response.decode("utf-8"))

        print("Connecting to device")
        self._socket.send(("device_connect " + self._device_id + "\r\n").encode())
        response = self._socket.recv(self._buffer_read_size)
        print(response.decode("utf-8"))

        print("Pausing data receiving")
        self._socket.send("pause ON\r\n".encode())
        response = self._socket.recv(self._buffer_read_size)
        print(response.decode("utf-8"))

        if self._acc:
            print("Suscribing to ACC")
            self._socket.send(("device_subscribe " + 'acc' + " ON\r\n").encode())
            response = self._socket.recv(self._buffer_read_size)
            print(response.decode("utf-8"))
        if self._bvp:
            print("Suscribing to BVP")
            self._socket.send(("device_subscribe " + 'bvp' + " ON\r\n").encode())
            response = self._socket.recv(self._buffer_read_size)
            print(response.decode("utf-8"))
        if self._gsr:
            print("Suscribing to GSR")
            self._socket.send(("device_subscribe " + 'gsr' + " ON\r\n").encode())
            response = self._socket.recv(self._buffer_read_size)
            print(response.decode("utf-8"))
        if self._tmp:
            print("Suscribing to Tmp")
            self._socket.send(("device_subscribe " + 'tmp' + " ON\r\n").encode())
            response = self._socket.recv(self._buffer_read_size)
            print(response.decode("utf-8"))

        print("Resuming data receiving")
        self._socket.send("pause OFF\r\n".encode())
        response = self._socket.recv(self._buffer_read_size)
        print(response.decode("utf-8"))

        self._log_status('Successfully connected to the E4 streamer.')

        if self._acc:
            infoACC = pylsl.StreamInfo('acc', 'ACC', 3, 32, 'int32', 'ACC-empatica_e4');
            global outletACC
            outletACC = pylsl.StreamOutlet(infoACC)
        if self._bvp:
            infoBVP = pylsl.StreamInfo('bvp', 'BVP', 1, 64, 'float32', 'BVP-empatica_e4');
            global outletBVP
            outletBVP = pylsl.StreamOutlet(infoBVP)
        if self._gsr:
            infoGSR = pylsl.StreamInfo('gsr', 'GSR', 1, 4, 'float32', 'GSR-empatica_e4');
            global outletGSR
            outletGSR = pylsl.StreamOutlet(infoGSR)
        if self._tmp:
            infoTmp = pylsl.StreamInfo('tmp', 'Tmp', 1, 4, 'float32', 'Tmp-empatica_e4');
            global outletTmp
            outletTmp = pylsl.StreamOutlet(infoTmp)

        return True

    #######################################
    ###### INTERFACE WITH THE SENSOR ######
    #######################################

    ## TODO: Add functions to control your sensor and acquire data.
    #        [Optional but probably useful]

    # A function to read a timestep of data for the first stream.
    def _read_data(self):
        # For example, may want to return the data for the timestep
        #  and the time at which it was received.
        try:
            # print("Starting LSL streaming")

            rawdata = self._socket.recvfrom(self._buffer_read_size)
            # print(rawdata)
            response = rawdata[0].decode("utf-8")

            # print("This is")
            #
            # print(type(response))
            # print(response)

            samples = response.split("\n")
            # print("SAMPLEs")
            # print(samples)

            streamer_list = []
            time_s_list = []
            data_list = []

            for i in range(len(samples) - 1):
                stream_type = samples[i].split()[0]
                if stream_type == "E4_Acc":
                    time_s = float(samples[i].split()[1].replace(',', '.'))
                    data = [int(samples[i].split()[2].replace(',', '.')), int(samples[i].split()[3].replace(',', '.')),
                            int(samples[i].split()[4].replace(',', '.'))]
                    # print(data)
                    outletACC.push_sample(data, timestamp=time_s)
                    # print('1')
                    # print(stream_type, time_s, data)
                    streamer_list.append(stream_type)
                    time_s_list.append(time_s)
                    data_list.append(data)
                if stream_type == "E4_Bvp":
                    time_s = float(samples[i].split()[1].replace(',', '.'))
                    data = float(samples[i].split()[2].replace(',', '.'))
                    outletBVP.push_sample([data], timestamp=time_s)
                    # print('2')
                    # print(stream_type, time_s, data)
                    streamer_list.append(stream_type)
                    time_s_list.append(time_s)
                    data_list.append(data)
                if stream_type == "E4_Gsr":
                    time_s = float(samples[i].split()[1].replace(',', '.'))
                    data = float(samples[i].split()[2].replace(',', '.'))
                    outletGSR.push_sample([data], timestamp=time_s)
                    # print('3')
                    # print(stream_type, time_s, data)
                    streamer_list.append(stream_type)
                    time_s_list.append(time_s)
                    data_list.append(data)
                if stream_type == "E4_Temperature":
                    time_s = float(samples[i].split()[1].replace(',', '.'))
                    data = float(samples[i].split()[2].replace(',', '.'))
                    outletTmp.push_sample([data], timestamp=time_s)
                    # print('4')
                    # print(stream_type, time_s, data)
                    streamer_list.append(stream_type)
                    time_s_list.append(time_s)
                    data_list.append(data)

            return (streamer_list, time_s_list, data_list)

        except:
            self._log_error('\n\n***ERROR reading from E4Streamer:\n%s\n' % traceback.format_exc())
            time.sleep(1)
            return (None, None, None)

    #####################
    ###### RUNNING ######
    #####################

    ## TODO: Continuously read data from your sensor.
    # Loop until self._running is False.
    # Acquire data from your sensor as desired, and for each timestep
    #  call self.append_data(device_name, stream_name, time_s, data).
    def _run(self):
        try:
            print("Streaming...")
            while self._running:

                # Read and store data for stream 1.
                (stream_type, time_s, data) = self._read_data()
                if time_s is not None:
                    for i in range (len(stream_type)):
                        if stream_type[i] == "E4_Acc":
                            self.append_data('ACC-empatica_e4', 'acc-values', time_s[i], data[i])
                        if stream_type[i] == "E4_Bvp":
                            self.append_data('BVP-empatica_e4', 'bvp-values', time_s[i], data[i])
                        if stream_type[i] == "E4_Gsr":
                            self.append_data('GSR-empatica_e4', 'gsr-values', time_s[i], data[i])
                        if stream_type[i] == "E4_Temperature":
                            self.append_data('Tmp-empatica_e4', 'tmp-values', time_s[i], data[i])
        except KeyboardInterrupt:  # The program was likely terminated
            pass
        except:
            self._log_error('\n\n***ERROR RUNNING E4Streamer:\n%s\n' % traceback.format_exc())
        finally:
            ## TODO: Disconnect from the sensor if desired.
            self._socket.close()

    # Clean up and quit
    def quit(self):
        ## TODO: Add any desired clean-up code.
        self._log_debug('E4Streamer quitting')
        self._socket.close()
        SensorStreamer.quit(self)

    ###########################
    ###### VISUALIZATION ######
    ###########################

    # Specify how the streams should be visualized.
    # Return a dict of the form options[device_name][stream_name] = stream_options
    #  Where stream_options is a dict with the following keys:
    #   'class': A subclass of Visualizer that should be used for the specified stream.
    #   Any other options that can be passed to the chosen class.
    def get_default_visualization_options(self, visualization_options=None):
        # Start by not visualizing any streams.
        processed_options = {}
        for (device_name, device_info) in self._streams_info.items():
            processed_options.setdefault(device_name, {})
            for (stream_name, stream_info) in device_info.items():
                processed_options[device_name].setdefault(stream_name, {'class': None})

        ## TODO: Specify whether some streams should be visualized.
        #        Examples of a line plot and a heatmap are below.
        #        To not visualize data, simply omit the following code and just leave each streamer mapped to the None class as shown above.
        # Use a line plot to visualize the weight.
        processed_options['ACC-empatica_e4']['acc-values'] = \
            {'class': LinePlotVisualizer, #HeatmapVisualizer
             'single_graph': True,   # Whether to show each dimension on a subplot or all on the same plot.
             'plot_duration_s': 15,  # The timespan of the x axis (will scroll as more data is acquired).
             'downsample_factor': 1, # Can optionally downsample data before visualizing to improve performance.
             }
        processed_options['BVP-empatica_e4']['bvp-values'] = \
            {'class': LinePlotVisualizer,  # HeatmapVisualizer
             'single_graph': True,  # Whether to show each dimension on a subplot or all on the same plot.
             'plot_duration_s': 15,  # The timespan of the x axis (will scroll as more data is acquired).
             'downsample_factor': 1,  # Can optionally downsample data before visualizing to improve performance.
             }
        processed_options['GSR-empatica_e4']['gsr-values'] = \
            {'class': LinePlotVisualizer,  # HeatmapVisualizer
             'single_graph': True,  # Whether to show each dimension on a subplot or all on the same plot.
             'plot_duration_s': 15,  # The timespan of the x axis (will scroll as more data is acquired).
             'downsample_factor': 1,  # Can optionally downsample data before visualizing to improve performance.
             }
        processed_options['Tmp-empatica_e4']['tmp-values'] = \
            {'class': LinePlotVisualizer,  # HeatmapVisualizer
             'single_graph': True,  # Whether to show each dimension on a subplot or all on the same plot.
             'plot_duration_s': 15,  # The timespan of the x axis (will scroll as more data is acquired).
             'downsample_factor': 1,  # Can optionally downsample data before visualizing to improve performance.
             }

        # Override the above defaults with any provided options.
        if isinstance(visualization_options, dict):
            for (device_name, device_info) in self._streams_info.items():
                if device_name in visualization_options:
                    device_options = visualization_options[device_name]
                    # Apply the provided options for this device to all of its streams.
                    for (stream_name, stream_info) in device_info.items():
                        for (k, v) in device_options.items():
                            processed_options[device_name][stream_name][k] = v

        return processed_options


#####################
###### TESTING ######
#####################
if __name__ == '__main__':
    # Configuration.
    duration_s = 30

    # Connect to the device(s).
    E4_streamer = E4Streamer(print_status=True, print_debug=False)
    E4_streamer.connect()

    # Run for the specified duration and periodically print the sample rate.
    print('\nRunning for %gs!' % duration_s)
    E4_streamer.run()
    print("Streamer Running Start")
    start_time_s = time.time()
    try:
        while time.time() - start_time_s < duration_s:
            time.sleep(2)
            # Print the sampling rates.
            msg = ' Duration: %6.2fs' % (time.time() - start_time_s)
            for device_name in E4_streamer.get_device_names():
                stream_names = E4_streamer.get_stream_names(device_name=device_name)
                for stream_name in stream_names:
                    num_timesteps = E4_streamer.get_num_timesteps(device_name, stream_name)
                    msg += ' | %s-%s: %6.2f Hz (%4d Timesteps)' % \
                           (device_name, stream_name, ((num_timesteps) / (time.time() - start_time_s)), num_timesteps)
            print(msg)
    except:
        pass

    # Stop the streamer.
    E4_streamer.stop()
    print('\n' * 2)
    print('=' * 75)
    print('Done!')
    print('\n' * 2)
