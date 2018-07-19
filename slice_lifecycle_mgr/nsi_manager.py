"""
## Copyright (c) 2015 SONATA-NFV, 2017 5GTANGO [, ANY ADDITIONAL AFFILIATION]
## ALL RIGHTS RESERVED.
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.
##
## Neither the name of the SONATA-NFV, 5GTANGO [, ANY ADDITIONAL AFFILIATION]
## nor the names of its contributors may be used to endorse or promote
## products derived from this software without specific prior written
## permission.
##
## This work has been performed in the framework of the SONATA project,
## funded by the European Commission under Grant number 671517 through
## the Horizon 2020 and 5G-PPP programmes. The authors would like to
## acknowledge the contributions of their colleagues of the SONATA
## partner consortium (www.sonata-nfv.eu).
##
## This work has been performed in the framework of the 5GTANGO project,
## funded by the European Commission under Grant number 761493 through
## the Horizon 2020 and 5G-PPP programmes. The authors would like to
## acknowledge the contributions of their colleagues of the 5GTANGO
## partner consortium (www.5gtango.eu).
"""
#!/usr/bin/python

import os, sys, logging, datetime, uuid, time, json
import dateutil.parser

import objects.nsi_content as nsi
import slice2ns_mapper.mapper as mapper
import slice_lifecycle_mgr.nsi_manager2repo as nsi_repo
import slice_lifecycle_mgr.nst_manager2catalogue as nst_catalogue

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("slicemngr:repo")
LOG.setLevel(logging.INFO)



#################### CREATE NSI SECTION ####################
def createNSI(nsi_jsondata):
    LOG.info("NSI_MNGR: Creating a new NSI")
    nstId = nsi_jsondata['nstId']
    catalogue_response = nst_catalogue.get_saved_nst(nstId)
    logging.debug('catalogue_response '+str(catalogue_response))
    nst_json = catalogue_response['nstd']
        
    #creates NSI with the received information
    NSI = parseNewNSI(nst_json, nsi_jsondata)
      
    #instantiates required NetServices by sending requests to Sonata SP
    requestsUUID_list = instantiateNetServices(nst_json['nstNsdIds'])
    logging.debug('requestsID_list: '+str(requestsUUID_list))

    #checks if all instantiations in Sonata SP are READY to store NSI object
    allInstantiationsReady = "NEW"
    while (allInstantiationsReady == "NEW" or allInstantiationsReady == "INSTANTIATING"):
      allInstantiationsReady = checkRequestsStatus(requestsUUID_list)
      time.sleep(30)
    
    #with all Services instantiated, it gets their uuids and keeps them inside the NSI information.
    for request_uuid_item in requestsUUID_list:
      instantiation_response = mapper.getRequestedNetServInstance(request_uuid_item)
      NSI.netServInstance_Uuid.append(instantiation_response['instance_uuid'])
    
    #updates the used NetSlice template ("usageState" and "referencedNSIs" parameters)
    addNSIinNST(nstId, nst_json, NSI.id)
    
    #Saving the NSI into the repositories and returning it
    NSI_string = vars(NSI)
    nsirepo_jsonresponse = nsi_repo.safe_nsi(NSI_string)
    return nsirepo_jsonresponse

def parseNewNSI(nst_json, nsi_json):
    LOG.info("NSI_MNGR: Parsing a new NSI from the user_info and the reference NST")
    uuid_nsi = str(uuid.uuid4())
    name = nsi_json['name']
    description = nsi_json['description']
    nstId = nsi_json['nstId']
    vendor = nst_json['vendor']
    nstName = nst_json['name']
    nstVersion = nst_json['version']
    flavorId = ""                                                                                            #TODO: where does it come from??
    sapInfo = ""                                                                                             #TODO: where does it come from??
    nsiState = "INSTANTIATED"
    instantiateTime = str(datetime.datetime.now().isoformat())
    terminateTime = ""
    scaleTime = ""
    updateTime = ""
    #netServInstance_Uuid = []                                                                  #values given when services are isntantiated by the SP
    
    NSI=nsi.nsi_content(uuid_nsi, name, description, nstId, vendor, nstName, nstVersion, flavorId, 
                  sapInfo, nsiState, instantiateTime, terminateTime, scaleTime, updateTime)
    return NSI

def instantiateNetServices(NetServicesIDs):
    #instantiates required NetServices by sending requests to Sonata SP
    requestsID_list = []
    logging.debug('NetServicesIDs: '+str(NetServicesIDs))   
    for uuidNetServ_item in NetServicesIDs:
      instantiation_response = mapper.net_serv_instantiate(uuidNetServ_item)
      LOG.info("NSI_MNGR: INSTANTIATION_RESPONSE: " + str(instantiation_response))
      requestsID_list.append(instantiation_response['id'])
    logging.debug('requestsID_list: '+str(requestsID_list))
    return requestsID_list

def checkRequestsStatus(requestsUUID_list):
    counter=0
    for resquestUUID_item in requestsUUID_list:
      getRequest_response = mapper.getRequestedNetServInstance(resquestUUID_item)
      LOG.info("NSI_MNGR: Information of the instantiated service: " + str(getRequest_response))
      if(getRequest_response['status'] == 'READY'):
        counter=counter+1
    if (counter == len(requestsUUID_list)):
      return "READY"
    elif getRequest_response['status'] == 'ERROR':
      return "ERROR"
    else:
      return "INSTANTIATING"

def addNSIinNST(nstId, nst_json, nsi_id):
    #Updates the usageState parameter
    if (nst_json['usageState'] == "NOT_IN_USE"):
      nstParameter2update = "usageState=IN_USE"
      updatedNST_jsonresponse = nst_catalogue.update_nst(nstParameter2update, nstId)
      
    #Updates (adds) the list of NSIref of original NST
    nst_refnsi_list = nst_json['referencedNSIs']
    nst_refnsi_list.append(nsi_id)
    nst_refnsi_string = (', '.join(nst_refnsi_list))
    nstParameter2update = "referencedNSIs="+nst_refnsi_string
    updatedNST_jsonresponse = nst_catalogue.update_nst(nstParameter2update, nstId)




#################### TERMINATE NSI SECTION ####################
def terminateNSI(nsiId, TerminOrder):
    LOG.info("NSI_MNGR: Terminate NSI with id: " +str(nsiId))
    jsonNSI = nsi_repo.get_saved_nsi(nsiId)
    
    #prepares the NSI object to manage with the info coming from repositories
    NSI=nsi.nsi_content(jsonNSI['uuid'], jsonNSI['name'], jsonNSI['description'], jsonNSI['nstId'], 
                    jsonNSI['vendor'], jsonNSI['nstName'], jsonNSI['nstVersion'], jsonNSI['flavorId'], jsonNSI['sapInfo'], 
                    jsonNSI['nsiState'], jsonNSI['instantiateTime'], jsonNSI['terminateTime'], 
                    jsonNSI['scaleTime'], jsonNSI['updateTime'], jsonNSI['netServInstance_Uuid'])
    
    #prepares the datetime values to work with them
    instan_time = dateutil.parser.parse(NSI.instantiateTime)
    if TerminOrder['terminateTime'] == "0":
      termin_time = 0
    else:
      termin_time = dateutil.parser.parse(TerminOrder['terminateTime'])
    
    #depending on the termin_time executes one action or another
    if termin_time == 0:
      NSI.terminateTime = str(datetime.datetime.now().isoformat())
      requestsUUID_list = NSI.netServInstance_Uuid
      if NSI.nsiState == "INSTANTIATED":
        #termination requests to all NetServiceInstances belonging to the NetSlice
        for requestUuid_item in requestsUUID_list:
          terminatedNetServ = mapper.net_serv_terminate(requestUuid_item)
      
        #checks if all instantiations in Sonata SP are TERMINATED to delete the NSI
        allInstantiationsReady = "READY"
        while (allInstantiationsReady == "READY"):
          allInstantiationsReady = checkTerminatesStatus(requestsUUID_list)
          time.sleep(30)
        
        repo_responseStatus = nsi_repo.delete_nsi(NSI.id)                         #TODO: terminate NSI = delete NSI from repos???
        NSI.nsiState = "TERMINATED"
        
        removeNSIinNST(NSI.id, NSI.nstId)                                           #TODO: check if it is the last NSI of the NST to change the "usageState" = "NOT_IN_USE"
        
      return (vars(NSI))
    
    elif instan_time < termin_time:                                               #TODO: manage future termination orders
      NSI.terminateTime = str(termin_time)
      NSI.nsiState = "TERMINATED"
      
      update_NSI = vars(NSI)
      repo_responseStatus = nsi_repo.update_nsi(update_NSI, nsiId)
      
      return (vars(NSI))                                                          #TODO: check if it is the last NSI of the NST to change the "usageState" = "NOT_IN_USE"
    else:
      return ("Please specify a correct termination: 0 to terminate inmediately or a time value later than: " + NSI.instantiateTime+ ", to terminate in the future.")

def checkTerminatesStatus(requestsUUID_list):
    counter=0
    for resquestUUID_item in requestsUUID_list:
      getRequest_response = mapper.getRequestedNetServInstance(resquestUUID_item)
      if(getRequest_response['status'] == 'TERMINATED'):
        counter=counter+1
    if (counter == len(requestsUUID_list)):
      return "TERMINATED"
    elif getRequest_response['status'] == 'ERROR':
      return "ERROR"
    else:
      return "READY"
      
def removeNSIinNST(nsi_id, nsi_nstid):
    #looks for the right NetSlice Template info
    catalogue_response = nst_catalogue.get_saved_nst(nsi_nstid)
    nst_json = catalogue_response['nstd']
    
    #deletes the terminated NetSlice instance uuid 
    nst_refnsi_list = nst_json['referencedNSIs']
    nst_refnsi_list.remove(nsi_id)
    nst_refnsi_string = (', '.join(nst_refnsi_list))
    nstParameter2update = "referencedNSIs="+nst_refnsi_string
    updatedNST_jsonresponse = nst_catalogue.update_nst(nstParameter2update, nsi_nstid)  
    
    #if there are no more NSI assigned to the NST, updates usageState parameter
    if not nst_json['referencedNSIs']:
      if (nst_json['usageState'] == "IN_USE"):  
        nstParameter2update = "usageState=NOT_IN_USE"
        updatedNST_jsonresponse = nst_catalogue.update_nst(nstParameter2update, nsi_nstid)    
    


#################### GET NSI SECTION ####################
def getNSI(nsiId):
    LOG.info("NSI_MNGR: Retrieving NSI with id: " +str(nsiId))
    nsirepo_jsonresponse = nsi_repo.get_saved_nsi(nsiId)

    return nsirepo_jsonresponse

def getAllNsi():
    LOG.info("NSI_MNGR: Retrieve all existing NSIs")
    nsirepo_jsonresponse = nsi_repo.getAll_saved_nsi()
    
    return nsirepo_jsonresponse