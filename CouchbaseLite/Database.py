# Database.py
#
# Copyright (c) 2019-2021 Couchbase, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import datetime
import math

from ._PyCBL import ffi, lib
from .common import *
from .Document import *

class DatabaseConfiguration:
    def __init__(self, directory):
        self.directory = directory

    def __repr__(self):
        return "DatabaseConfiguration['" + self.directory + "']"
    # TODO: Add encryption key for EE support


class Database (CBLObject):
    def __init__(self, name, config =None):
        if config != None:
            dirSlice = stringParam(config.directory)
            cblConfig = ffi.new("CBLDatabaseConfiguration*", [dirSlice])
        else:
            cblConfig = ffi.NULL
        self.name = name
        self.listeners = set()
        CBLObject.__init__(self, lib.CBLDatabase_Open(stringParam(name), cblConfig, gError),
                           "Couldn't open database " + name, gError)

    def __repr__(self):
        return "Database['" + self.name + "']"

    def close(self):
        if not lib.CBLDatabase_Close(self._ref, gError):
            print ("WARNING: Database.close() failed")

    def delete(self):
        if not lib.CBLDatabase_Delete(self._ref, gError):
            raise CBLException("Couldn't delete database", gError)

    @staticmethod
    def deleteFile(name, dir):
        if lib.CBL_DeleteDatabase(stringParam(name), stringParam(dir), gError):
            return True
        elif gError.code == 0:
            return False
        else:
            raise CBLException("Couldn't delete database file", gError)

    def compact(self):
        if not lib.CBLDatabase_Compact(self._ref, gError):
            raise CBLException("Couldn't compact database", gError)

    # Attributes:

    def getPath(self):
        return sliceToString(lib.CBLDatabase_Path(self._ref))
    path = property(getPath)

    @property
    def config(self):
        c_config = lib.CBLDatabase_Config(self._ref)
        dir = sliceToString(c_config.directory)
        return DatabaseConfiguration(dir)

    @property
    def count(self):
        return lib.CBLDatabase_Count(self._ref)

    # Documents:

    def getDocument(self, id):
        return Document._get(self, id)

    def getMutableDocument(self, id):
        return MutableDocument._get(self, id)

    def saveDocument(self, doc, concurrency = FailOnConflict):
        doc._prepareToSave()
        if not lib.CBLDatabase_SaveDocumentWithConcurrencyControl(self._ref, doc._ref, concurrency, gError):
            raise CBLException("Couldn't save document", gError)

    def deleteDocument(self, id):
        if not lib.CBLDatabase_DeleteDocument(self._ref, stringParam(id), gError):
            raise CBLException("Couldn't delete document", gError)

    def purgeDocument(self, id):
        if not lib.CBLDatabase_PurgeDocument(self._ref, stringParam(id), gError):
            raise CBLException("Couldn't purge document", gError)

    def __getitem__(self, id):
        return self.getMutableDocument(id)

    def __setitem__(self, id, doc):
        if id != doc.id:
            raise CBLException("key does not match document ID")
        self.saveDocument(doc)

    def __delitem__(self, id):
        self.deleteDocument(id)

    # Batch operations:  (`with db: ...`)

    def __enter__(self):
        if not lib.CBLDatabase_BeginTransaction(self._ref, gError):
            raise CBLException("Couldn't begin a transaction", gError)

    def __exit__(self, exc_type, exc_value, traceback):
        commit = not exc_type
        if not lib.CBLDatabase_EndTransaction(self._ref, commit, gError) and commit:
            raise CBLException("Couldn't commit a transaction", gError)

    # TODO: Some way to abort the transaction w/o raising an exception

    # Expiration:
    
    def getDocumentExpiration(self, id):
        exp = lib.CBLDatabase_GetDocumentExpiration(self._ref, id, gError)
        if exp > 0:
            return datetime.fromtimestamp(exp)
        elif exp == 0:
            return None
        else:
            raise CBLException("Couldn't get document's expiration", gError)
            
    def setDocumentExpiration(self, id, expDateTime):
        timestamp = 0
        if expDateTime != None:
            timestamp = math.ceil(expDateTime.timestamp)
        if not lib.CBLDatabase_SetDocumentExpiration(self._ref, id, timestamp, gError):
            raise CBLException("Couldn't set document's expiration", gError)
            

    # Listeners:

    def addListener(self, listener):
        handle = ffi.new_handle(listener)
        self.listeners.add(handle)
        c_token = lib.CBLDatabase_AddChangeListener(self._ref, lib.databaseListenerCallback, handle)
        return ListenerToken(self, handle, c_token)

    def addDocumentListener(self, docID, listener):
        handle = ffi.new_handle(listener)
        self.listeners.add(handle)
        c_token = lib.CBLDatabase_AddDocumentChangeListener(self._ref, docID,
                                                            lib.databaseListenerCallback, handle)
        return ListenerToken(self, handle, c_token)

    def removeListener(self, token):
        token.remove()


@ffi.def_extern()
def databaseListenerCallback(context, db, numDocs, c_docIDs):
    docIDs = []
    for i in range(numDocs):
        docIDs.append(sliceToString(c_docIDs[i]))
    listener = ffi.from_handle(context)
    listener(docIDs)

@ffi.def_extern()
def documentListenerCallback(context, db, docID):
    listener = ffi.from_handle(context)
    listener(sliceToString(docID))
