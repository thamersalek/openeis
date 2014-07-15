'''
Copyright (c) 2014, Battelle Memorial Institute
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met: 

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer. 
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies, 
either expressed or implied, of the FreeBSD Project.
'''
'''
This material was prepared as an account of work sponsored by an 
agency of the United States Government.  Neither the United States 
Government nor the United States Department of Energy, nor Battelle,
nor any of their employees, nor any jurisdiction or organization 
that has cooperated in the development of these materials, makes 
any warranty, express or implied, or assumes any legal liability 
or responsibility for the accuracy, completeness, or usefulness or 
any information, apparatus, product, software, or process disclosed,
or represents that its use would not infringe privately owned rights.

Reference herein to any specific commercial product, process, or 
service by trade name, trademark, manufacturer, or otherwise does 
not necessarily constitute or imply its endorsement, recommendation, 
r favoring by the United States Government or any agency thereof, 
or Battelle Memorial Institute. The views and opinions of authors 
expressed herein do not necessarily state or reflect those of the 
United States Government or any agency thereof.

PACIFIC NORTHWEST NATIONAL LABORATORY
operated by BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
under Contract DE-AC05-76RL01830
'''
import datetime
from applications import BaseAlgorithm, Results, logging
from os import path

from openeis.applications import DriverApplicationBaseClass, ConfigDescriptor,  \
    OutputDescriptor, ConfigDescriptor
import logging

class Application(DriverApplicationBaseClass):
    """
    Air-side HVAC Auto-Retuning diagnostic to check if the supply-air
    temperature is too low.
    """
    def __init__(self,reheat_valve_threshold=None,data_window=None,
                percent_reheat_threshold=None,number_of_zones=None,
                setpoint_allowable_deviation=None,rht_on_threshold=None,*args,**kwargs):
        super( ).__init__(*args,**kwargs)
        self.dat_stpt_values = []
        self.dat_values = []
        self.timestamp = []
        self.total_reheat = 0
        self.pre_requiste_messages = []
        self.pre_msg_time = []

        '''Pre-requisite messages'''
        self.pre_msg  = 'Supply fan is off, current data will not be used for diagnostics.'
        self.pre_msg1  = 'Verify that point names in diagnostic match OpenEIS data-type names.'

        '''Algorithm thresholds (Configurable)'''
        self.data_window = float(data_window)
        self.number_of_zones = int(number_of_zones)
        self.reheat_valve_threshold = float(reheat_valve_threshold)
        self.percent_reheat_threshold = float(percent_reheat_threshold)
        self.setpoint_allowable_deviation = float(setpoint_allowable_deviation)
        self.rht_on_threshold = float(rht_on_threshold)
        self.reheat=[[] for i in range(self.number_of_zones)]

        '''Diagnostic Point Names (Must match Openeis data-type names)'''
        self.fan_status_name = "SupplyFanStatus"
        self.zone_reheat_name = "ZoneReheatValvePosition"
        self.da_temp_name = "DischargeAirTemperature"
        self.da_temp_stpt_name = "DischargeAirTemperatureSetPoint"

    @classmethod
    def get_config_parameters(cls):
        #Called by UI
        return {
            'data_window': ConfigDescriptor(float, 'Data Window'),
            'number_of_zones': ConfigDescriptor(int, 'Number of Zones'),
            'reheat_valve_threshold': ConfigDescriptor(float, 'Teminal Box Reheat Valve Position'),
            'percent_reheat_threshold': ConfigDescriptor(float, 'Excess Terminal Reheat Threshold'),
            'setpoint_allowable_deviation': ConfigDescriptor(float, 'Supply-air Temperate Deadband'),
            'rht_on_threshold': ConfigDescriptor(float, 'Zone Is Reheating Threshold')
           }

    @classmethod
    def required_input(cls):
        #Called by UI
        return {
            'fan_status': InputDescriptor('SupplyFanStatus', 'AHU Supply Fan Status', count_min=1),
            'da_temp_stpt' : InputDescriptor('DischargeAirTemperatureSetPoint','AHU Discharge-air temperature set-point', count_min=0),
            'da_temp' : InputDescriptor('DischargeAirTemperature','AHU Discharge-air Temperature', count_min=1),
            'zone_rht_vlv': InputDescriptor('ZoneReheatValvePosition','For accurate results this diagnostic requires \
                                                    terminal box data for all for a particular AHU', count_min=2)
            }
           
    def report(self):
    #Called by UI to create Viz
        """
        Describe how to present output to user
        Display this viz with these columns from this table
    
        display_elements is a list of display objects specifying viz and columns
        for that viz
        """
        pass

    @classmethod
    def output_format(cls, input_object):
        # Called when app is staged
        """
        Output will have the date, hour, and respective load.
        To be graphed in a heat map later.
        """
        topics = input_object.get_topics()
        diagnostic_topic = topics['load'][0]  #Not sure about the topics['load']
        diagnostic_topic_parts = diagnostic_topic.split('/')
        output_topic_base = diagnostic_topic_parts[:-1]
        datetime_topic = '/'.join(output_topic_base+['airside_low_dat_diagnostic', 'date'])
        message_topic = '/'.join(output_topic_base+['airside_low_dat_diagnostic', 'message'])
        output_needs = {
            'Diagnostic_Message': {
                'date-time': OutputDescriptor('datetime', date_topic),
                'diagnostic-message': OutputDescriptor('string', message_topic)
                }
            }
        return output_needs

    def drop_partial_lines (self): 
        return True

    def run(self,current_time, points):
        self.pre_msg_time.append(current_time)    
        """
        Check algorithm pre-quisites and assemble data set for analysis.
        """
        device_dict = {}
        diagnostic_result = Results()
        
        for key, value in points.iteritems():
            device_dict[key.lower()] = value
            
        message_check =  datetime.timedelta(minutes=(self.data_window))
       
        if (self.pre_msg_time[-1]-self.pre_msg_time[0]) >= message_check:
            msg_lst = [self.pre_msg, self.pre_msg1]
            for item in msg_lst:
                if self.pre_requiste_messages.count(item) > (0.25)*len(self.pre_msg_time):
                    diagnostic_result.log(item, logging.INFO)
            self.pre_requiste_messages = []
            self.pre_msg_time = []

        for key, value in device_dict.iteritems():
            if self.fan_status_name in key:
                if int(value) == 0:
                    self.pre_requiste_messages.append(sef.pre_msg)
                    return diagnostic_result

        self.timestamp.append(current_time)

        for key, value in device_dict.iteritems():
            if self.zone_reheat_name in key:
                if value > self.rht_on_threshold:
                    self.total_reheat = self.total_reheat + 1
            if self.da_temp_name in key:
                self.dat_values.append(value)
            if self.da_temp_stpt_name in key:
                self.dat_stpt_values.append(value)

            for x in range(1, self.number_of_zones + 1):
                if self.zone_reheat_name in key and str(x) in key:
                    self.reheat[x-1].append(value)
                    
        if not self.dat_values or not self.reheat:
            self.pre_requiste_messages.append(self.pre_msg1)
            return diagnostic_result

        time_check =  datetime.timedelta(minutes=self.data_window)

        if ((self.timestamp[-1]-self.timestamp[0]) >= time_check and
            len(self.dat_values) > 10):
            diagnostic_result = self.low_dat_sp(diagnostic_result)
        return diagnostic_result

    def low_dat_sp(self, result):
        """
        If the detected problems(s) are consistent then generate a fault message(s).
        If auto-correction is enabled and a problem is detected apply correction action.
        """
        time_d = self.timestamp[-1]-self.timestamp[0]
        time_d = int(time_d.total_seconds()/60) + 1

        avg_zones_reheat = self.total_reheat/(time_d*self.number_of_zones)*100

        temp = []
        for lists in self.reheat:
            for values in lists:
                temp.append(values)
        reheat_coil_average = (sum(temp))/(len(temp))

        if self.dat_stpt_values:
            avg_dat_stpt = (sum(self.dat_stpt_values))/(len(self.dat_stpt_values))
            set_point_tracking = [abs(x-y) for x,y in zip(self.dat_stpt_values, self.dat_values)]
            set_point_tracking = sum(set_point_tracking)/(len(set_point_tracking)*avg_dat_stpt)*100
            if set_point_tracking > self.setpoint_allowable_deviation:
                result.log('Supply-air temperature is deviating significantly from the supply-air temperature set point.', logging.INFO)

        self.timestamp = []
        self.dat_stpt_values = []
        self.dat_values = []
        self.pre_requiste_messages = []
        self.pre_msg_time = []
        self.reheat=[[] for i in range(self.number_of_zones)]
        self.total_reheat = 0

        if (reheat_coil_average > self.reheat_valve_threshold and
            avg_zones_reheat > self.percent_reheat_threshold):
            diagnostic_message = 'The discharge-air temperature has been detected to be too low.'
        else:
            diagnostic_message = 'No re-tuning opportunity was detected during the low discharge-air temperature diagnostic.'
        result.log(diagnostic_message, logging.INFO)
        return result     