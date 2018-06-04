#!/usr/bin/python

import os, sys, logging, datetime, uuid, time, json
import dateutil.parser

import objects.nsi_content as nsi
import slice2ns_mapper.mapper as mapper
import slice_lifecycle_mgr.nsi_manager2repo as nsi_repo
import slice_lifecycle_mgr.nst_manager2catalogue as nst_catalogue
import database.database as db

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("slicemngr:repo")
LOG.setLevel(logging.INFO)

##### CREATE NSI SECTION #####
#MAIN FUNCTION: createNSI(...)
#related functions: parseNetSliceInstance(...), instantiateNetServices(...), checkRequestsStatus(...)
def createNSI(nsi_jsondata):
    LOG.info("NSI_MNGR: Creating a new NSI")
    nstId = nsi_jsondata['nstId']
    catalogue_response = nst_catalogue.get_saved_nst(nstId)
    nst_json = catalogue_response['nstd']
        
    #creates NSI with the received information
    NSI = parseNewNSI(nst_json, nsi_jsondata)
      
    #instantiates required NetServices by sending requests to Sonata SP
    requestsID_list = instantiateNetServices(nst_json['nstNsdIds'])
    
    #checks if all instantiations in Sonata SP are READY to store NSI object
    allInstantiationsReady = False
    while (allInstantiationsReady == False):
      allInstantiationsReady = checkRequestsStatus(requestsID_list)
      #time.sleep(5)
    
    #with all Services instantiated, it gets their uuids and keeps them inside the NSI information.
    for request_uuid_item in requestsID_list:
      instantiation_response = mapper.getRequestedNetServInstance(request_uuid_item)
      NSI.netServInstance_Uuid.append(instantiation_response['service_instance_uuid'])

    #Updating the the usageState parameter of the slelected NST
    if (nst_json['usageState'] == "NOT_IN_USE"):  
      #nst_json['usageState'] = "IN_USE"
      nstParameter2update = "usageState=IN_USE"
      updatedNST_jsonresponse = nst_catalogue.update_nst(nstParameter2update, nstId)
    
    #Saving the NSI into the repositories and returning it
    NSI_string = vars(NSI)
    nsirepo_jsonresponse = nsi_repo.safe_nsi(NSI_string)
    return nsirepo_jsonresponse

def parseNewNSI(nst_json, nsi_json):
    uuid_nsi = str(uuid.uuid4())
    name = nsi_json['name']
    description = nsi_json['description']
    nstId = nsi_json['nstId']
    vendor = nst_json['vendor']
    nstInfoId = nst_json['name'] + "made by " + nst_json['author'] + "belonging to " + nst_json['vendor']
    flavorId = ""                                                                                            #TODO: where does it come from??
    sapInfo = ""                                                                                             #TODO: where does it come from??
    nsiState = "INSTANTIATED"
    instantiateTime = str(datetime.datetime.now().isoformat())
    terminateTime = ""
    scaleTime = ""
    updateTime = ""
    #netServInstance_Uuid = []    #these values are given later on, when the services are isntantiated and have a uuid given by the SP
    
    NSI=nsi.nsi_content(uuid_nsi, name, description, nstId, vendor, nstInfoId, flavorId, sapInfo, 
                  nsiState, instantiateTime, terminateTime, scaleTime, updateTime)
    return NSI

def instantiateNetServices(NetServicesIDs):
    #instantiates required NetServices by sending requests to Sonata SP
    requestsID_list = []   
    for uuidNetServ_item in NetServicesIDs:
      instantiation_response = mapper.net_serv_instantiate(uuidNetServ_item)
      requestsID_list.append(instantiation_response['id'])
    return requestsID_list

def checkRequestsStatus(requestsID_list):
    counter=0
    for resquestID_item in requestsID_list:
      getRequest_response = mapper.getRequestedNetServInstance(resquestID_item)  
      if(getRequest_response['status'] == 'READY'):
        counter=counter+1
    
    if (counter == len(requestsID_list)):
      return True
    else:
      return False

##### TERMINATE NSI SECTION #####
def terminateNSI(nsiId, TerminOrder):
    LOG.info("NSI_MNGR: Terminate NSI with id: " +str(nsiId))
    jsonNSI = nsi_repo.get_saved_nsi(nsiId)
    
    #prepares the NSI object to manage with the info coming from repositories
    NSI=nsi.nsi_content(jsonNSI['uuid'], jsonNSI['name'], jsonNSI['description'], jsonNSI['nstId'], 
                    jsonNSI['vendor'], jsonNSI['nstInfoId'], jsonNSI['flavorId'], jsonNSI['sapInfo'], 
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
      if NSI.nsiState == "INSTANTIATED":
        #termination requests to all NetServiceInstances belonging to the NetSlice
        for ServInstanceUuid_item in NSI.netServInstance_Uuid:
          terminatedNetServ = mapper.net_serv_terminate(ServInstanceUuid_item)     #TODO: validate all related NetService instances are terminated
      
      repo_responseStatus = nsi_repo.delete_nsi(NSI.id)
      
      NSI.nsiState = "TERMINATED"
      return (vars(NSI))                                                          #TODO: check if it is the last NSI of the NST to change the "usageState" = "NOT_IN_USE"
    
    elif instan_time < termin_time:                                               #TODO: manage future termination orders
      NSI.terminateTime = str(termin_time)
      NSI.nsiState = "TERMINATED"
      
      update_NSI = vars(NSI)
      repo_responseStatus = nsi_repo.update_nsi(update_NSI, nsiId)
      
      return (vars(NSI))                                                          #TODO: check if it is the last NSI of the NST to change the "usageState" = "NOT_IN_USE"
    else:
      return ("Please specify a correct termination: 0 to terminate inmediately or a time value later than: " + NSI.instantiateTime+ ", to terminate in the future.")
    

##### GET NSI SECTION #####
def getNSI(nsiId):
    LOG.info("NSI_MNGR: Retrieving NSI with id: " +str(nsiId))
    nsirepo_jsonresponse = nsi_repo.get_saved_nsi(nsiId)

    return nsirepo_jsonresponse

def getAllNsi():
    LOG.info("NSI_MNGR: Retrieve all existing NSIs")
    nsirepo_jsonresponse = nsi_repo.getAll_saved_nsi()
    
    return nsirepo_jsonresponse